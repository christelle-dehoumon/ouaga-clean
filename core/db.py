"""Deux bases SQLite séparées, même schéma : data/reel.db (vrais signalements) et data/sim.db (tout ce qui est simulé).

get_db(mode) ouvre l'une ou l'autre ; aucune fonction n'ouvre les deux à la fois (pas d'ATTACH, donc aucune jointure
possible entre réel et simulé). Chemins : variables REEL_DB et SIM_DB, sinon paths.reel_db et paths.sim_db de la
configuration. Mode WAL, transactions courtes (with conn:), une connexion par requête.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import get_config, resolve, section

MODES = ("reel", "sim")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('depotoir', 'nettoyage')),
  statut TEXT NOT NULL CHECK (statut IN ('a_verifier', 'confirme', 'rejete', 'nettoye')),
  lat REAL NOT NULL, lon REAL NOT NULL,
  photo_path TEXT, photo_hash TEXT,
  reported_at TEXT NOT NULL,
  alertes TEXT NOT NULL DEFAULT '[]',
  nb_signalements INTEGER NOT NULL DEFAULT 1,
  duplicate_of TEXT,
  source TEXT NOT NULL CHECK (source IN ('reel', 'sim')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_statut ON reports(statut, type);
CREATE INDEX IF NOT EXISTS idx_reports_photo ON reports(photo_hash);
CREATE TABLE IF NOT EXISTS historique(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id TEXT NOT NULL REFERENCES reports(id),
  qui TEXT NOT NULL CHECK (qui IN ('citoyen', 'brigade', 'mairie', 'systeme')),
  quand TEXT NOT NULL,
  action TEXT NOT NULL,
  de_statut TEXT, vers_statut TEXT, de_type TEXT, vers_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_historique_report ON historique(report_id, id);
CREATE TABLE IF NOT EXISTS ecartes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quand TEXT NOT NULL, motif_code TEXT NOT NULL, motif TEXT NOT NULL,
  payload_resume TEXT NOT NULL,
  lat REAL, lon REAL,
  resolu INTEGER NOT NULL DEFAULT 0,
  report_id TEXT
);
CREATE TABLE IF NOT EXISTS plans(
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, mode TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios(
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, plan_id TEXT, label TEXT,
  params TEXT NOT NULL, events TEXT NOT NULL, results TEXT NOT NULL,
  compute_ms INTEGER, mode TEXT
);
CREATE TABLE IF NOT EXISTS sim_dumpsites(
  id TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, kg REAL NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS road_cuts(
  edge_id TEXT PRIMARY KEY, lat REAL, lon REAL, created_at TEXT NOT NULL
);
"""

_READY: set[str] = set()
_LOCK = threading.Lock()


def now() -> str:
    """Horodatage UTC ISO 8601."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def db_path(mode: str) -> Path:
    """Fichier de la base du mode demandé ; ValueError si le mode n'est ni reel ni sim."""
    if mode not in MODES:
        raise ValueError(f"Mode « {mode} » inconnu : reel ou sim.")
    env = os.environ.get("REEL_DB" if mode == "reel" else "SIM_DB")
    if env:
        return Path(env) if env == ":memory:" else resolve(env)
    default = "data/reel.db" if mode == "reel" else "data/sim.db"
    return resolve(section(get_config(), "paths").get(f"{mode}_db") or default)


def get_db(mode: str) -> sqlite3.Connection:
    """Connexion à reel.db ou sim.db (schéma créé si besoin, WAL, clés étrangères, lignes en dictionnaires)."""
    path = db_path(mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    key = f"{mode}:{path}"
    if key not in _READY:
        with _LOCK:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            _READY.add(key)
    return conn


def reset(mode: str) -> None:
    """Vide toutes les tables d'une base (remise à zéro)."""
    conn = get_db(mode)
    try:
        with conn:
            for table in ("historique", "ecartes", "reports", "plans", "scenarios", "sim_dumpsites", "road_cuts"):
                conn.execute(f"DELETE FROM {table}")  # noqa: S608 - noms de tables fixes
    finally:
        conn.close()


def save_plan(mode: str, plan: dict[str, Any]) -> str:
    """Enregistre un plan (identifiant rendu unique) et renvoie son identifiant."""
    conn = get_db(mode)
    try:
        base, pid, n = plan["plan_id"], plan["plan_id"], 2
        with conn:
            while conn.execute("SELECT 1 FROM plans WHERE id=?", (pid,)).fetchone():
                pid, n = f"{base}_{n}", n + 1
            plan["plan_id"] = pid
            conn.execute("INSERT INTO plans(id, created_at, mode, body) VALUES(?,?,?,?)",
                         (pid, now(), mode, json.dumps(plan, ensure_ascii=False, default=str)))
        return pid
    finally:
        conn.close()


def load_plan(plan_id: str) -> tuple[str, dict[str, Any]] | None:
    """(mode, plan) d'un plan enregistré, cherché dans reel.db puis sim.db."""
    for mode in MODES:
        conn = get_db(mode)
        try:
            row = conn.execute("SELECT body FROM plans WHERE id=?", (plan_id,)).fetchone()
        finally:
            conn.close()
        if row:
            return mode, json.loads(row["body"])
    return None
