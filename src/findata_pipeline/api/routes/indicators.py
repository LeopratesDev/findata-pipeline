"""Indicadores: listagem, ultimo valor vigente e historico paginado."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ...database import Database
from .. import services
from ..deps import get_db
from ..schemas import HistoryResponse, IndicatorInfo, LatestResponse

router = APIRouter(prefix="/api/v1/indicators", tags=["indicadores"])


@router.get("", response_model=list[IndicatorInfo])
def list_indicators() -> list[IndicatorInfo]:
    return services.list_indicators()


@router.get(
    "/{series_id}/latest",
    response_model=LatestResponse,
    responses={404: {"description": "Serie desconhecida"}},
)
def latest(series_id: str, db: Database = Depends(get_db)) -> LatestResponse:
    return services.get_latest(db, series_id)


@router.get(
    "/{series_id}/history",
    response_model=HistoryResponse,
    responses={404: {"description": "Serie desconhecida"}, 422: {"description": "Parametros invalidos"}},
)
def history(
    series_id: str,
    start: Optional[date] = Query(default=None, description="Data inicial (ISO) inclusiva"),
    end: Optional[date] = Query(default=None, description="Data final (ISO) inclusiva"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_history: bool = Query(default=False, description="Inclui versoes aposentadas"),
    db: Database = Depends(get_db),
) -> HistoryResponse:
    return services.get_history(
        db,
        series_id,
        start.isoformat() if start else None,
        end.isoformat() if end else None,
        limit,
        offset,
        include_history,
    )
