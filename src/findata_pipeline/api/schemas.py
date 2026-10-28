"""Contratos Pydantic da API.

Decisao de precisao: ``value`` trafega como **string** (texto canonico do
Decimal, ex. "0.040168"), nunca convertido para float. Isso preserva a
precisao decimal exigida em dados financeiros. Documentado no OpenAPI.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class IndicatorInfo(BaseModel):
    series_id: str = Field(examples=["BCB-SGS-12"])
    sgs_code: int = Field(examples=[12])
    name: str = Field(examples=["CDI"])
    unit: str = Field(examples=["percent_per_day"])
    periodicity: str = Field(examples=["business_day"])


class Observation(BaseModel):
    series_id: str = Field(examples=["BCB-SGS-12"])
    source: str = Field(examples=["BCB-SGS"])
    reference_date: str = Field(examples=["2024-01-02"], description="Data do indicador (ISO 8601)")
    value: str = Field(examples=["0.040168"], description="Valor como texto decimal (nunca float)")
    unit: str = Field(examples=["percent_per_day"])
    collected_at: str = Field(examples=["2026-10-28T14:54:37Z"], description="Quando foi coletado (ISO-UTC)")
    version: int = Field(examples=[1])
    is_current: bool = Field(examples=[True])
    superseded_at: Optional[str] = Field(default=None, description="Quando a versao foi aposentada")


class LatestResponse(BaseModel):
    series_id: str
    has_data: bool
    observation: Optional[Observation] = None


class HistoryResponse(BaseModel):
    series_id: str
    total: int = Field(description="Total de registros que casam com o filtro")
    limit: int
    offset: int
    count: int = Field(description="Quantidade nesta pagina")
    items: list[Observation]


class RejectionInfo(BaseModel):
    series_id: str
    raw_data: Optional[str] = None
    raw_value: Optional[str] = None
    reason: str
    collected_at: str


class RunSummary(BaseModel):
    id: int
    started_at: str
    finished_at: Optional[str] = None
    source: str
    status: str = Field(examples=["done"], description="running | done | completed_with_errors | failed")
    extracted: int = 0
    valid: int = 0
    rejected: int = 0
    inserted: int = 0
    duplicates: int = 0
    revisions: int = 0
    trigger: Optional[str] = Field(default=None, examples=["api"])
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    requested_series: Optional[str] = None
    error_detail: Optional[str] = None
    duration_seconds: Optional[float] = Field(default=None, description="finished_at - started_at")


class RunDetail(RunSummary):
    rejections: list[RejectionInfo] = []


class RunListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[RunSummary]


class RunCreateRequest(BaseModel):
    series_ids: Optional[list[str]] = Field(
        default=None, description="Series a coletar; ausente = todas as do registro"
    )
    days: Optional[int] = Field(
        default=None, ge=1, le=3650, description="Janela de coleta em dias (default do servidor)"
    )


class RunCreateResponse(BaseModel):
    run_id: int
    status: str = Field(examples=["running"])
    message: str = Field(examples=["Execucao aceita e iniciada em background."])


class RunStatusResponse(BaseModel):
    run_id: int
    status: str
    finished_at: Optional[str] = None
    error_detail: Optional[str] = None


class StatusResponse(BaseModel):
    observations_count: int
    indicators: int
    last_successful_collection: Optional[str] = None
    last_run: Optional[RunSummary] = None


class HealthResponse(BaseModel):
    status: str = Field(default="ok", examples=["ok"])


class ReadyResponse(BaseModel):
    ready: bool
    database: bool
    detail: Optional[str] = None


class ReportInfo(BaseModel):
    report_id: str = Field(examples=["report_20261028_145437.json"])
    size_bytes: int
    modified_at: str


class ErrorResponse(BaseModel):
    detail: str
