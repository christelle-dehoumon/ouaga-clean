"""Connexion SQLite et schéma de la base de données.

Le Validator (core/validation/rules.py) instancie lui-même sqlite3 et exécute
ce SCHEMA. Ce module l'exporte pour que d'autres modules puissent le réutiliser
sans dupliquer la définition.
"""
import os
import sqlite3

DB_PATH = os.environ.get("REPORTS_DB", "data/reports.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, lat REAL, lon REAL, size TEXT, reported_at TEXT,
  received_at TEXT, status TEXT, reason_code TEXT, reason TEXT,
  duplicate_of TEXT, confirmations INTEGER DEFAULT 1, photo_hash TEXT,
  source TEXT, accuracy_m REAL,
  validated_by TEXT, validated_at TEXT, validation_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_status ON reports(status);
"""


def get_connection(path: str = DB_PATH) -> sqlite3.Connection:
    """Retourne une connexion SQLite avec row_factory activé."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
