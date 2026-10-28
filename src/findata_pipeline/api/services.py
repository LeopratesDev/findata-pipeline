"""Camada de servicos: orquestra Database/pipeline e devolve contratos.

Testavel sem HTTP - recebe um Database (e, para escrita, um PipelineRunner)
e nao conhece FastAPI. As rotas apenas chamam estas funcoes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import config
from ..database import Database
from . import schemas


class UnknownSeriesError(Exception):
    """series_id nao existe no registro de series."""


class ReportNotFoundError(Exception):
    """Relatorio solicitado nao existe."""


class InvalidReportIdError(Exception):
    """report_id invalido (ex.: tentativa de path traversal)."""


# --- indicadores -----------------------------------------------------------
def list_indicators() -> list[schemas.IndicatorInfo]:
    return [
        schemas.IndicatorInfo(
            series_id=s.series_id, sgs_code=s.sgs_code, name=s.name,
            unit=s.unit, periodicity=s.periodicity,
        )
        for s in config.SERIES.values()
    ]


def _require_series(series_id: str) -> None:
    if series_id not in config.SERIES:
        raise UnknownSeriesError(series_id)


def _to_observation(row: dict) -> schemas.Observation:
    return schemas.Observation(
        series_id=row["series_id"],
        source=row["source"],
        reference_date=row["reference_date"],
        value=row["value"],
        unit=row["unit"],
        collected_at=row["collected_at"],
        version=row["version"],
        is_current=bool(row["is_current"]),
        superseded_at=row["superseded_at"],
    )


def get_latest(db: Database, series_id: str) -> schemas.LatestResponse:
    _require_series(series_id)
    row = db.get_latest(series_id)
    if row is None:
        return schemas.LatestResponse(series_id=series_id, has_data=False, observation=None)
    return schemas.LatestResponse(
        series_id=series_id, has_data=True, observation=_to_observation(row)
    )


def get_history(
    db: Database,
    series_id: str,
    start: Optional[str],
    end: Optional[str],
    limit: int,
    offset: int,
    include_history: bool,
) -> schemas.HistoryResponse:
    _require_series(series_id)
    total = db.count_observations_query(series_id, start, end, include_history)
    rows = db.query_observations(series_id, start, end, limit, offset, include_history)
    items = [_to_observation(r) for r in rows]
    return schemas.HistoryResponse(
        series_id=series_id, total=total, limit=limit, offset=offset,
        count=len(items), items=items,
    )


# --- execucoes (runs) ------------------------------------------------------
def _duration_seconds(started_at: Optional[str], finished_at: Optional[str]) -> Optional[float]:
    if not started_at or not finished_at:
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        delta = datetime.strptime(finished_at, fmt) - datetime.strptime(started_at, fmt)
    except ValueError:
        return None
    return delta.total_seconds()


def _to_run_summary(row: dict) -> schemas.RunSummary:
    return schemas.RunSummary(
        id=row["id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        source=row["source"],
        status=row["status"] or "unknown",
        extracted=row["extracted"] or 0,
        valid=row["valid"] or 0,
        rejected=row["rejected"] or 0,
        inserted=row["inserted"] or 0,
        duplicates=row["duplicates"] or 0,
        revisions=row["revisions"] or 0,
        trigger=row["trigger"],
        window_start=row["window_start"],
        window_end=row["window_end"],
        requested_series=row["requested_series"],
        error_detail=row["error_detail"],
        duration_seconds=_duration_seconds(row["started_at"], row["finished_at"]),
    )


def list_runs(db: Database, limit: int, offset: int) -> schemas.RunListResponse:
    total = db.count_runs()
    rows = db.get_runs(limit, offset)
    return schemas.RunListResponse(
        total=total, limit=limit, offset=offset,
        items=[_to_run_summary(r) for r in rows],
    )


def get_run_detail(db: Database, run_id: int) -> Optional[schemas.RunDetail]:
    row = db.get_run(run_id)
    if row is None:
        return None
    summary = _to_run_summary(row)
    rejections = [
        schemas.RejectionInfo(
            series_id=r["series_id"], raw_data=r["raw_data"], raw_value=r["raw_value"],
            reason=r["reason"], collected_at=r["collected_at"],
        )
        for r in db.get_rejections(run_id)
    ]
    return schemas.RunDetail(**summary.model_dump(), rejections=rejections)


def get_run_status(db: Database, run_id: int) -> Optional[schemas.RunStatusResponse]:
    row = db.get_run(run_id)
    if row is None:
        return None
    return schemas.RunStatusResponse(
        run_id=run_id, status=row["status"] or "unknown",
        finished_at=row["finished_at"], error_detail=row["error_detail"],
    )


# --- status geral ----------------------------------------------------------
def get_status(db: Database) -> schemas.StatusResponse:
    runs = db.get_runs(limit=1, offset=0)
    last_run = _to_run_summary(runs[0]) if runs else None
    last_ok = db.get_last_successful_run()
    return schemas.StatusResponse(
        observations_count=db.count_observations(),
        indicators=len(config.SERIES),
        last_successful_collection=last_ok["finished_at"] if last_ok else None,
        last_run=last_run,
    )


# --- relatorios ------------------------------------------------------------
_ALLOWED_REPORT_SUFFIXES = {".json", ".csv"}


def list_reports() -> list[schemas.ReportInfo]:
    directory = Path(config.REPORTS_DIR)
    if not directory.is_dir():
        return []
    reports = []
    for path in sorted(directory.iterdir(), reverse=True):
        if path.is_file() and path.suffix in _ALLOWED_REPORT_SUFFIXES:
            stat = path.stat()
            reports.append(
                schemas.ReportInfo(
                    report_id=path.name,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                )
            )
    return reports


def resolve_report_path(report_id: str) -> Path:
    """Resolve o caminho de um relatorio, bloqueando path traversal.

    So aceita arquivos .json/.csv dentro de REPORTS_DIR. Qualquer caminho
    que escape do diretorio -> InvalidReportIdError. Inexistente -> ReportNotFoundError.
    """
    base = Path(config.REPORTS_DIR).resolve()
    candidate = (base / report_id).resolve()
    if not candidate.is_relative_to(base):
        raise InvalidReportIdError(report_id)
    if candidate.suffix not in _ALLOWED_REPORT_SUFFIXES:
        raise InvalidReportIdError(report_id)
    if not candidate.is_file():
        raise ReportNotFoundError(report_id)
    return candidate
