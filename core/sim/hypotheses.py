"""Hypothèses de simulation — valeurs lues dans la configuration.

Règle du membre C : aucun nombre de simulation n'est écrit dans le code de
règle. Quand une clé manque dans ``config/commune_config.json`` (cas actuel du
rayon de patrouille de la brigade), on utilise une valeur par défaut **déclarée
ici**, explicitement étiquetée « à valider » dans la sortie de ``run_scenario``.
Une demande d'ajout des clés manquantes est écrite dans
``docs/demandes_membre_C.md`` : ce module n'a pas à modifier la configuration,
qui appartient à un autre membre.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[2]

# Valeurs par défaut du membre C, utilisées seulement si la configuration
# ne fournit pas la clé. Chacune doit apparaître dans la sortie « hypotheses ».
DEFAUTS_C: dict[str, Any] = {
    "brigade_radius_m": 500,
    "brigade_patrols_per_day": 2,
    "brigade_success_rate": 0.22,
    "menage_dump_rate_served": 0.35,
    "menage_dump_rate_unserved": 0.78,
    "precollect_pass_rate": 0.88,
    "precollect_breakdown_rate": 0.04,
    "max_events_per_day": 6,
}


def charger_configuration() -> dict[str, Any]:
    """Configuration commune, lue depuis le disque à chaque appel."""
    try:
        import json

        with (RACINE / "config" / "commune_config.json").open(encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except Exception:
        return {}


def _config_valeur(config: dict[str, Any], section: str, cle: str, defaut: Any) -> Any:
    bloc = config.get(section)
    if isinstance(bloc, dict) and cle in bloc:
        return bloc[cle]
    return defaut


def hypotheses(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Dictionnaire ``cle -> {valeur, source, note}`` pour l'étiquetage UI."""
    cfg = config if isinstance(config, dict) else charger_configuration()
    modele = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    params = cfg.get("params") if isinstance(cfg.get("params"), dict) else {}
    resume: dict[str, dict[str, Any]] = {}

    def ajouter(cle: str, valeur: Any, source: str) -> None:
        resume[cle] = {
            "valeur": valeur,
            "source": source,
            "note": "hypothèse à valider avec la mairie",
        }

    for cle in ("waste_kg_per_person_day", "persons_per_building", "precollect_radius_m",
                "truck_trips_per_day", "cost_per_km_truck", "cost_per_km_tricycle",
                "truck_speed_kmh", "tricycle_speed_kmh", "service_min_per_stop",
                "shift_minutes", "dumpsite_kg_by_size"):
        if cle in modele:
            ajouter(cle, modele[cle], "config/commune_config.json:model")
    for cle in ("population", "subscription_rate", "trucks", "truck_capacity_kg",
                "tricycles", "tricycle_capacity_kg", "frequency_per_week", "budget"):
        if cle in params:
            ajouter(cle, params[cle], "config/commune_config.json:params")

    for cle, valeur in DEFAUTS_C.items():
        # Une clé présente dans la configuration gagne toujours sur le défaut C.
        if cle in modele:
            ajouter(cle, modele[cle], "config/commune_config.json:model")
        else:
            ajouter(cle, valeur, "défaut membre C (clé absente de la configuration)")

    if "brigade_radius_m" not in modele:
        resume["brigade_radius_m"]["note"] += " — demander l'ajout de model.brigade_radius_m"
    return resume


def valeur(hyp: dict[str, dict[str, Any]], cle: str, repli: Any = None) -> Any:
    """Accès court à une valeur d'hypothèse."""
    entree = hyp.get(cle)
    if isinstance(entree, dict) and "valeur" in entree:
        return entree["valeur"]
    return repli
