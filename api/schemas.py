"""Modèles Pydantic pour les réponses de l'API signalements.

Le POST /api/reports accepte un dict brut (Request.json()) pour ne jamais
renvoyer un 422 FastAPI. Ces modèles ne servent qu'aux réponses.
"""
from typing import Optional
from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: Optional[str] = None
    status: str                      # accepte | rejete | a_verifier
    reason_code: str
    reason: str
    duplicate_of: Optional[str] = None
    ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    ok: bool
    reports: int


class StatsResponse(BaseModel):
    total: int
    par_statut: dict
    par_motif: dict


class ValidateResponse(BaseModel):
    updated: bool


class ResetResponse(BaseModel):
    reset: bool
