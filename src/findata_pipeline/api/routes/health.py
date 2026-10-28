"""Saude e diagnostico: /health e /ready.

/health = o processo responde (sempre 200 se vivo). /ready = dependencias
prontas (banco acessivel e com as tabelas). Distinguir os dois importa para
orquestracao (health check do container vs. prontidao real).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from ...database import Database
from ..schemas import HealthResponse, ReadyResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["saude"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={503: {"description": "Dependencias indisponiveis"}},
)
def ready(request: Request, response: Response) -> ReadyResponse:
    db = None
    try:
        db = Database(request.app.state.db_path)
        # consulta leve que so funciona se a tabela existir
        db.count_observations()
        return ReadyResponse(ready=True, database=True)
    except Exception as exc:  # banco inacessivel ou sem schema
        logger.warning("readiness falhou: %s", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(ready=False, database=False, detail="banco indisponivel")
    finally:
        if db is not None:
            db.close()
