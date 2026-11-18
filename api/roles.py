"""Accès par rôle sans compte : un code simple par rôle, envoyé dans l'en-tête X-Role-Code.

Codes : variables d'environnement BRIGADE_CODE et MAIRIE_CODE, sinon les codes de démonstration de la configuration
(section roles, publics, documentés dans le README). Code absent ou faux : 401. Rôle non autorisé : 403.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable

from fastapi import HTTPException, Request

from core.config import get_config, section

ROLES = ("brigade", "mairie")


def role_codes() -> dict[str, str]:
    """Code de chaque rôle (environnement d'abord)."""
    cfg = section(get_config(), "roles")
    return {"brigade": os.environ.get("BRIGADE_CODE") or str(cfg.get("brigade_code_default") or ""),
            "mairie": os.environ.get("MAIRIE_CODE") or str(cfg.get("mairie_code_default") or "")}


def role_of(request: Request) -> str:
    """Rôle correspondant au code de l'en-tête ; 401 si absent ou inconnu."""
    code = request.headers.get(section(get_config(), "roles").get("header") or "X-Role-Code") or ""
    if not code:
        raise HTTPException(401, "Code d'accès manquant : envoyer l'en-tête X-Role-Code (brigade ou mairie).")
    for role, expected in role_codes().items():
        if expected and hmac.compare_digest(code.encode(), expected.encode()):
            return role
    raise HTTPException(401, "Code d'accès incorrect.")


def require(*allowed: str) -> Callable[[Request], str]:
    """Dépendance FastAPI : renvoie le rôle si autorisé, 401 sinon, 403 si le rôle n'a pas le droit."""
    def check(request: Request) -> str:
        role = role_of(request)
        if role not in allowed:
            raise HTTPException(403, f"Action réservée à : {', '.join(allowed)} (rôle actuel : {role}).")
        return role
    return check
