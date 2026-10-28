"""Resumo do estado da aplicacao: /api/v1/status."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...database import Database
from .. import services
from ..deps import get_db
from ..schemas import StatusResponse

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status", response_model=StatusResponse)
def get_status(db: Database = Depends(get_db)) -> StatusResponse:
    return services.get_status(db)
