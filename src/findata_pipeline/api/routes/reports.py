"""Relatorios: listagem e download seguro (bloqueia path traversal)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import services
from ..schemas import ReportInfo

router = APIRouter(prefix="/api/v1/reports", tags=["relatorios"])

_MEDIA_TYPES = {".json": "application/json", ".csv": "text/csv"}


@router.get("", response_model=list[ReportInfo])
def list_reports() -> list[ReportInfo]:
    return services.list_reports()


@router.get(
    "/{report_id}/download",
    responses={
        200: {"content": {"application/json": {}, "text/csv": {}}},
        400: {"description": "Identificador invalido"},
        404: {"description": "Relatorio inexistente"},
    },
)
def download_report(report_id: str) -> FileResponse:
    try:
        path = services.resolve_report_path(report_id)
    except services.InvalidReportIdError as exc:
        raise HTTPException(status_code=400, detail="identificador de relatorio invalido") from exc
    except services.ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail="relatorio inexistente") from exc
    return FileResponse(
        path, media_type=_MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
        filename=path.name,
    )
