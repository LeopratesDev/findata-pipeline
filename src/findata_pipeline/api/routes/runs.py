"""Execucoes do pipeline: listagem, detalhe, criacao (202) e status."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ... import config
from ...database import Database
from .. import services
from ..deps import get_db, get_runner, require_write_auth
from ..runner import PipelineRunner, RunConflictError
from ..schemas import (
    RunCreateRequest,
    RunCreateResponse,
    RunDetail,
    RunListResponse,
    RunStatusResponse,
)

router = APIRouter(prefix="/api/v1/runs", tags=["execucoes"])


@router.get("", response_model=RunListResponse)
def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_db),
) -> RunListResponse:
    return services.list_runs(db, limit, offset)


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    responses={404: {"description": "Execucao inexistente"}},
)
def get_run(run_id: int, db: Database = Depends(get_db)) -> RunDetail:
    detail = services.get_run_detail(db, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="execucao inexistente")
    return detail


@router.post(
    "",
    response_model=RunCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Execucao aceita e iniciada em background"},
        409: {"description": "Ja existe uma execucao em andamento"},
        422: {"description": "Parametros invalidos"},
    },
    dependencies=[Depends(require_write_auth)],
)
def create_run(
    body: RunCreateRequest | None = None,
    runner: PipelineRunner = Depends(get_runner),
) -> RunCreateResponse:
    body = body or RunCreateRequest()

    if body.series_ids:
        invalidas = [s for s in body.series_ids if s not in config.SERIES]
        if invalidas:
            raise HTTPException(
                status_code=422, detail=f"series desconhecidas: {invalidas}"
            )

    days = body.days or config.DEFAULT_COLLECTION_DAYS
    end = date.today()
    start = end - timedelta(days=days)

    try:
        run_id = runner.request_run(
            series_ids=body.series_ids, start=start, end=end, trigger="api"
        )
    except RunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return RunCreateResponse(
        run_id=run_id,
        status="running",
        message="Execucao aceita e iniciada em background. Consulte /status para acompanhar.",
    )


@router.get(
    "/{run_id}/status",
    response_model=RunStatusResponse,
    responses={404: {"description": "Execucao inexistente"}},
)
def run_status(run_id: int, db: Database = Depends(get_db)) -> RunStatusResponse:
    result = services.get_run_status(db, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="execucao inexistente")
    return result
