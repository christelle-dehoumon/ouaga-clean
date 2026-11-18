"""Machine à états d'un cas (seul endroit où elle est définie) et historique des transitions.

Transitions valides (rôle, action, type, statut) -> (type, statut) :
1. brigade  confirmer          depotoir  a_verifier -> depotoir  confirme
2. brigade  rejeter            depotoir  a_verifier -> depotoir  rejete
3. mairie   marquer_nettoye    depotoir  confirme   -> nettoyage a_verifier
4. brigade  confirmer          nettoyage a_verifier -> nettoyage nettoye    (jamais supprimé de la base)
5. brigade  rejeter            nettoyage a_verifier -> nettoyage rejete
6. mairie   remettre_a_verifier depotoir rejete     -> depotoir  a_verifier
7. mairie   remettre_a_verifier nettoyage rejete    -> nettoyage a_verifier
Toute autre transition : 409. Un rôle sans droit sur l'action : 403. Chaque transition valide écrit une ligne
d'historique dans la même transaction ; l'UPDATE est conditionné à l'état lu, donc rejouer une décision donne 409.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.db import now

TRANSITIONS: dict[tuple[str, str, str, str], tuple[str, str]] = {
    ("brigade", "confirmer", "depotoir", "a_verifier"): ("depotoir", "confirme"),
    ("brigade", "rejeter", "depotoir", "a_verifier"): ("depotoir", "rejete"),
    ("mairie", "marquer_nettoye", "depotoir", "confirme"): ("nettoyage", "a_verifier"),
    ("brigade", "confirmer", "nettoyage", "a_verifier"): ("nettoyage", "nettoye"),
    ("brigade", "rejeter", "nettoyage", "a_verifier"): ("nettoyage", "rejete"),
    ("mairie", "remettre_a_verifier", "depotoir", "rejete"): ("depotoir", "a_verifier"),
    ("mairie", "remettre_a_verifier", "nettoyage", "rejete"): ("nettoyage", "a_verifier"),
}
ACTION_ROLES = {action: {r for (r, a, _t, _s) in TRANSITIONS if a == action} for (_r, action, _t, _s) in TRANSITIONS}
LABELS = {"a_verifier": "à vérifier", "confirme": "confirmé", "rejete": "rejeté", "nettoye": "nettoyé",
          "depotoir": "dépotoir", "nettoyage": "nettoyage"}


class LifecycleError(Exception):
    """Transition refusée ; status = code HTTP (404, 403 ou 409), message en français."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _history(conn: sqlite3.Connection, report_id: str, who: str, action: str, before: tuple[str | None, str | None],
             after: tuple[str | None, str | None], when: str) -> None:
    """Une ligne d'historique (jamais modifiée ensuite)."""
    conn.execute("INSERT INTO historique(report_id, qui, quand, action, de_type, de_statut, vers_type, vers_statut) "
                 "VALUES(?,?,?,?,?,?,?,?)", (report_id, who, when, action, before[0], before[1], after[0], after[1]))


def create(conn: sqlite3.Connection, report: dict[str, Any], who: str = "citoyen") -> None:
    """Nouveau cas (type depotoir, statut a_verifier) et sa ligne d'historique, dans une seule transaction."""
    when = now()
    with conn:
        conn.execute("INSERT INTO reports(id, type, statut, lat, lon, photo_path, photo_hash, reported_at, alertes, "
                     "nb_signalements, duplicate_of, source, created_at, updated_at, cell_y, cell_x) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (report["id"], "depotoir", "a_verifier", report["lat"], report["lon"], report.get("photo_path"),
                      report.get("photo_hash"), report["reported_at"], json.dumps(report.get("alertes", [])), 1, None,
                      report["source"], when, when, *(report.get("cell") or (None, None))))
        _history(conn, report["id"], who, "creation", (None, None), ("depotoir", "a_verifier"), when)


def reinforce(conn: sqlite3.Connection, report_id: str, alert: str) -> int:
    """Doublon : le cas existant est renforcé (nb_signalements + 1, alerte), historique « renforce ». Renvoie le compte."""
    when = now()
    with conn:
        row = conn.execute("SELECT type, statut, alertes, nb_signalements FROM reports WHERE id=?", (report_id,)).fetchone()
        alerts = sorted(set(json.loads(row["alertes"] or "[]")) | {alert})
        conn.execute("UPDATE reports SET nb_signalements = nb_signalements + 1, alertes=?, updated_at=? WHERE id=?",
                     (json.dumps(alerts), when, report_id))
        _history(conn, report_id, "systeme", "renforce", (row["type"], row["statut"]), (row["type"], row["statut"]), when)
    return int(row["nb_signalements"]) + 1


def apply(conn: sqlite3.Connection, report_id: str, role: str, action: str) -> dict[str, Any]:
    """Applique une action ; LifecycleError (404, 403, 409) sinon. Renvoie {id, type, statut}."""
    if action not in ACTION_ROLES:
        raise LifecycleError(409, f"Action « {action} » inconnue.")
    if role not in ACTION_ROLES[action]:
        raise LifecycleError(403, f"Le rôle « {role} » ne peut pas « {action} » : réservé à "
                                  f"{', '.join(sorted(ACTION_ROLES[action]))}.")
    when = now()
    with conn:
        row = conn.execute("SELECT type, statut FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None:
            raise LifecycleError(404, f"Cas « {report_id} » introuvable.")
        target = TRANSITIONS.get((role, action, row["type"], row["statut"]))
        if target is None:
            raise LifecycleError(409, f"Transition impossible : un cas de type « {LABELS[row['type']]} » au statut "
                                      f"« {LABELS[row['statut']]} » ne peut pas recevoir l'action « {action} ».")
        cur = conn.execute("UPDATE reports SET type=?, statut=?, updated_at=? WHERE id=? AND type=? AND statut=?",
                           (*target, when, report_id, row["type"], row["statut"]))
        if cur.rowcount != 1:  # un autre appel a changé le cas entre la lecture et l'écriture
            raise LifecycleError(409, "Le cas a changé entre-temps : recharger et réessayer.")
        _history(conn, report_id, role, action, (row["type"], row["statut"]), target, when)
    return {"id": report_id, "type": target[0], "statut": target[1]}


def history(conn: sqlite3.Connection, report_id: str) -> list[dict[str, Any]]:
    """Historique d'un cas, dans l'ordre : [{qui, quand, action, de, vers}]."""
    rows = conn.execute("SELECT * FROM historique WHERE report_id=? ORDER BY id", (report_id,)).fetchall()
    return [{"qui": r["qui"], "quand": r["quand"], "action": r["action"],
             "de": {"type": r["de_type"], "statut": r["de_statut"]}, "vers": {"type": r["vers_type"], "statut": r["vers_statut"]}}
            for r in rows]
