"""Historique et comparaison des scénarios — membre C.

Les entrées sont de petits dictionnaires JSONAutonomes : aucun état dans un
fichier, aucune base de données, aucune dépendance. Le tableau de bord peut
ainsi garder les deux derniers scénarios comparables même sans réseau.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# Clés comparables : elles viennent du plan (A) et de la simulation (C).
CLES_PLAN = ("cout_annuel_m_fcfa", "tonnes_rue_par_jour")
CLES_SIM = ("part_ramassee", "depotoirs_restants")


def nouvel_id(prefixe: str = "s") -> str:
    return prefixe + "_" + uuid.uuid4().hex[:10]


def _nombre(source: dict[str, Any] | None, cle: str) -> float | None:
    if not isinstance(source, dict):
        return None
    valeur = source.get(cle)
    try:
        return round(float(valeur), 3)
    except (TypeError, ValueError):
        return None


def _paquet(entree: dict[str, Any]) -> dict[str, Any]:
    """Normalise une entrée d'historique, même si elle vient d'un ancien format."""
    plan = entree.get("plan") if isinstance(entree.get("plan"), dict) else {}
    simulation = entree.get("simulation") if isinstance(entree.get("simulation"), dict) else {}
    if not plan and isinstance(entree.get("coherence"), dict):
        plan = entree["coherence"]
    if not simulation and "part_ramassee" in entree:
        simulation = entree
    return {"plan": plan, "simulation": simulation}


def resumer(entree: dict[str, Any]) -> dict[str, Any]:
    paquet = _paquet(entree)
    return {
        "id": entree.get("id") or entree.get("scenario_id"),
        "plan_id": entree.get("plan_id"),
        "cree_le": entree.get("cree_le"),
        "params": entree.get("params") or entree.get("parametres") or {},
        "plan": {
            "mode": paquet["plan"].get("mode", "—"),
            "cout_annuel_m_fcfa": _nombre(paquet["plan"], "cout_annuel_m_fcfa"),
            "tonnes_rue_par_jour": _nombre(paquet["plan"], "tonnes_rue_par_jour"),
            "points": paquet["plan"].get("points"),
        },
        "simulation": {
            "part_ramassee": _nombre(paquet["simulation"], "part_ramassee"),
            "depotoirs_restants": paquet["simulation"].get("depotoirs_restants"),
            "moteur": paquet["simulation"].get("moteur"),
        },
    }


def comparer(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compare B − A. Ne lève jamais et garde les clés historiques du dashboard."""
    try:
        pa, pb = _paquet(a), _paquet(b)
        ca, cb = _nombre(pa["plan"], "cout_annuel_m_fcfa"), _nombre(pb["plan"], "cout_annuel_m_fcfa")
        ta, tb = _nombre(pa["plan"], "tonnes_rue_par_jour"), _nombre(pb["plan"], "tonnes_rue_par_jour")
        sa, sb = _nombre(pa["simulation"], "part_ramassee"), _nombre(pb["simulation"], "part_ramassee")
        da = pa["simulation"].get("depotoirs_restants")
        db = pb["simulation"].get("depotoirs_restants")
        return {
            "diff_cout": None if ca is None or cb is None else round(cb - ca, 3),
            "diff_tonnes": None if ta is None or tb is None else round(tb - ta, 1),
            "diff_part_ramassee": None if sa is None or sb is None else round(sb - sa, 3),
            "diff_depotoirs": None if not isinstance(da, int) or not isinstance(db, int) else db - da,
            "scenarios": [resumer(a), resumer(b)],
        }
    except Exception as exc:
        return {
            "diff_cout": None,
            "diff_tonnes": None,
            "diff_part_ramassee": None,
            "diff_depotoirs": None,
            "warnings": [f"Comparaison indisponible : {type(exc).__name__} — {exc}"],
        }


class HistoriqueScenarios:
    """Historique en mémoire, borné, des scénarios calculés et simulés."""

    def __init__(self, limite: int = 50):
        self.limite = max(1, int(limite))
        self._entrees: list[dict[str, Any]] = []

    def ajouter(self, entree: dict[str, Any]) -> dict[str, Any]:
        donnees = dict(entree)
        donnees.setdefault("id", nouvel_id())
        donnees.setdefault("cree_le", datetime.now(timezone.utc).isoformat())
        self._entrees.insert(0, donnees)
        del self._entrees[self.limite:]
        return donnees

    def liste(self) -> list[dict[str, Any]]:
        return [resumer(e) for e in self._entrees]

    def get(self, identifiant: str) -> dict[str, Any] | None:
        return next((e for e in self._entrees if e.get("id") == identifiant), None)

    def par_plan(self, plan_id: str) -> dict[str, Any] | None:
        return next((e for e in self._entrees if e.get("plan_id") == plan_id), None)

    def attacher_simulation(self, plan_id: str, simulation: dict[str, Any]) -> dict[str, Any] | None:
        entree = self.par_plan(plan_id)
        if entree is None:
            return None
        entree["simulation"] = simulation
        return entree

    def comparer_ids(self, a_id: str, b_id: str) -> dict[str, Any]:
        a = self.get(a_id) or self.par_plan(a_id)
        b = self.get(b_id) or self.par_plan(b_id)
        if a is None or b is None:
            return {"error": "scénario introuvable", "warnings": [f"A={a_id!r}, B={b_id!r}"]}
        return comparer(a, b)
