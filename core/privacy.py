"""Floutage des visages et des plaques d'immatriculation, côté serveur, AVANT tout stockage.

- La photo reçue n'existe qu'en mémoire ; seule la version floutée et réencodée en JPEG est écrite (le réencodage
  supprime aussi les métadonnées EXIF, dont la position GPS de l'appareil).
- Détection : cascades Haar d'OpenCV fournies dans le paquet opencv-python-headless (visages de face et de profil,
  plaques), aucun modèle téléchargé à l'exécution.
- Floutage : zone élargie de privacy.margin_ratio, flou gaussien fort puis pixelisation.
- Fiabilité limitée (cascades anciennes, plaques entraînées sur un modèle russe) : mesurée sur des images de test
  dans docs/mesures.md, aucun taux annoncé sans mesure. Si la détection échoue (erreur), l'option la plus sûre est
  appliquée : TOUTE l'image est floutée et le cas reçoit l'alerte FLOUTAGE_NON_VERIFIE.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import cv2
import numpy as np

from core.config import get_config, section


class PhotoError(ValueError):
    """Photo illisible (pas une image décodable)."""


@lru_cache(maxsize=8)
def _cascade(name: str) -> cv2.CascadeClassifier:
    """Cascade Haar du paquet OpenCV ; erreur si absente (jamais téléchargée)."""
    clf = cv2.CascadeClassifier(cv2.data.haarcascades + name)
    if clf.empty():
        raise RuntimeError(f"Cascade OpenCV introuvable : {name}")
    return clf


def _merge(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Fusionne les rectangles qui se chevauchent (plusieurs cascades détectent souvent le même visage)."""
    merged: list[list[int]] = []
    for x, y, w, h in sorted(boxes):
        for m in merged:
            if x < m[0] + m[2] and m[0] < x + w and y < m[1] + m[3] and m[1] < y + h:
                x1, y1 = min(m[0], x), min(m[1], y)
                m[2], m[3] = max(m[0] + m[2], x + w) - x1, max(m[1] + m[3], y + h) - y1
                m[0], m[1] = x1, y1
                break
        else:
            merged.append([x, y, w, h])
    return [tuple(m) for m in merged]  # type: ignore[misc]


def _boxes(gray: np.ndarray, names: list[str], cfg: dict[str, Any], neighbors: int, min_size: tuple[int, int],
           mirror: bool = False) -> list[tuple[int, int, int, int]]:
    """Rectangles détectés par une liste de cascades (et sur l'image miroir pour les profils), fusionnés."""
    out: list[tuple[int, int, int, int]] = []
    for name in names:
        clf = _cascade(name)
        for img, flip in ((gray, False), (cv2.flip(gray, 1), True)) if mirror else ((gray, False),):
            found = clf.detectMultiScale(img, scaleFactor=float(cfg.get("scale_factor") or 1.1),
                                         minNeighbors=neighbors, minSize=min_size)
            for x, y, w, h in found if len(found) else []:
                out.append((int(gray.shape[1] - x - w) if flip else int(x), int(y), int(w), int(h)))
    return _merge(out)


def _plate_regions(img: np.ndarray, gray: np.ndarray, cfg: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    """Zones de texte sombre sur fond clair, de forme allongée : plaques probables (et quelques panneaux)."""
    if not cfg.get("enabled"):
        return []
    h, w = gray.shape
    kw, kh = (int(v) for v in cfg.get("kernel") or (13, 5))
    rect = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, rect)
    grad = np.absolute(cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=-1))
    grad = (255 * (grad - grad.min()) / (grad.max() - grad.min() + 1e-6)).astype("uint8")
    grad = cv2.morphologyEx(cv2.GaussianBlur(grad, (5, 5), 0), cv2.MORPH_CLOSE, rect)
    mask = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    mask = cv2.dilate(cv2.erode(mask, None, iterations=2), None, iterations=2)
    light = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    out = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        aspect = bw / max(bh, 1)
        if (float(cfg.get("aspect_min", 2)) <= aspect <= float(cfg.get("aspect_max", 6.5))
                and float(cfg.get("min_width_ratio", 0.04)) * w <= bw <= float(cfg.get("max_width_ratio", 0.6)) * w
                and bh >= int(cfg.get("min_height_px", 8))
                and light[y:y + bh, x:x + bw].mean() / 255 >= float(cfg.get("min_light_fill", 0.45))):
            out.append((x, y, bw, bh))
    return out


def _blur_region(img: np.ndarray, x: int, y: int, w: int, h: int, cfg: dict[str, Any]) -> None:
    """Flou gaussien fort puis pixelisation d'une zone élargie, en place."""
    m = float(cfg.get("margin_ratio") or 0.25)
    x0, y0 = max(int(x - w * m), 0), max(int(y - h * m), 0)
    x1, y1 = min(int(x + w * (1 + m)), img.shape[1]), min(int(y + h * (1 + m)), img.shape[0])
    roi = img[y0:y1, x0:x1]
    if roi.size == 0:
        return
    k = max(int(max(roi.shape[:2]) * float(cfg.get("blur_kernel_ratio") or 0.5)) | 1, 3)
    roi = cv2.GaussianBlur(roi, (k, k), 0)
    block = max(int(cfg.get("pixel_block") or 12), 2)
    small = cv2.resize(roi, (max(roi.shape[1] // block, 1), max(roi.shape[0] // block, 1)), interpolation=cv2.INTER_AREA)
    img[y0:y1, x0:x1] = cv2.resize(small, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST)


def blur_photo(data: bytes, cfg: dict[str, Any] | None = None) -> tuple[bytes, dict[str, Any]]:
    """(JPEG flouté, rapport {faces, plates, status}) ; PhotoError si ce n'est pas une image."""
    pcfg = section(cfg or get_config(), "privacy")
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR) if data else None
    if img is None or img.size == 0:
        raise PhotoError("Photo illisible : ce n'est pas une image JPEG ou PNG.")
    side = int(pcfg.get("max_side_px") or 1600)
    scale = min(1.0, side / max(img.shape[:2]))
    if scale < 1:
        img = cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    report: dict[str, Any] = {"faces": 0, "plates": 0, "status": "ok", "width": img.shape[1], "height": img.shape[0]}
    try:
        gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        size = int(pcfg.get("min_size_px") or 24)
        faces = _boxes(gray, list(pcfg.get("face_cascades") or []), pcfg, int(pcfg.get("min_neighbors") or 5),
                       (size, size), mirror=True)
        plates = _boxes(gray, list(pcfg.get("plate_cascades") or []), pcfg,
                        int(pcfg.get("plate_min_neighbors") or 3), (size, size // 3))
        plates = _merge(plates + _plate_regions(img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), section(pcfg, "plate_morph")))
        for box in faces + plates:
            _blur_region(img, *box, pcfg)
        report.update(faces=len(faces), plates=len(plates))
    except Exception as exc:  # détection impossible : on floute tout (jamais de photo brute)
        _blur_region(img, 0, 0, img.shape[1], img.shape[0], {**pcfg, "margin_ratio": 0})
        report.update(status="blur_all", error=type(exc).__name__)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(pcfg.get("jpeg_quality") or 80)])
    if not ok:
        raise PhotoError("Photo impossible à réencoder.")
    return buf.tobytes(), report
