"""Validacao e normalizacao dos registros brutos do SGS.

O validador e *ciente da serie*: unidade e limites de sanidade vem do
registro de series, porque o mesmo valor numerico e plausivel para uma
serie e impossivel para outra (uma variacao mensal de 50% no IPCA vs uma
taxa diaria de 50% na CDI). Registros invalidos nunca sao descartados em
silencio - cada um retorna com um motivo legivel por maquina.

Precisao: valores sao convertidos com ``Decimal`` (nunca ``float``) e
guardados como texto canonico, preservando as casas decimais recebidas.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

from .config import SOURCE, SeriesConfig

logger = logging.getLogger(__name__)

_INPUT_DATE_FMT = "%d/%m/%Y"


@dataclass
class Rejection:
    series_id: str
    raw_data: Optional[str]
    raw_value: Optional[str]
    reason: str


@dataclass
class ValidationResult:
    valid: list[dict] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)


def utc_now_iso() -> str:
    """Instante atual em ISO 8601 (UTC), usado como collected_at."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_decimal(raw_value: str) -> Decimal:
    # Aceita virgula defensivamente, embora a API use ponto.
    return Decimal(raw_value.strip().replace(",", "."))


def validate_records(
    records: Iterable[dict],
    series: SeriesConfig,
    collected_at: Optional[str] = None,
) -> ValidationResult:
    """Valida e normaliza um lote de registros de uma unica serie."""
    collected_at = collected_at or utc_now_iso()
    result = ValidationResult()
    seen_dates: set[str] = set()

    for record in records:
        raw_data = record.get("data")
        raw_value = record.get("valor")

        # 1) campos obrigatorios
        if not raw_data or raw_value in (None, ""):
            result.rejected.append(
                Rejection(series.series_id, raw_data, raw_value, "missing_required_field")
            )
            continue

        # 2) data dd/MM/yyyy -> ISO 8601
        try:
            reference_date = (
                datetime.strptime(raw_data, _INPUT_DATE_FMT).date().isoformat()
            )
        except (ValueError, TypeError):
            result.rejected.append(
                Rejection(series.series_id, raw_data, raw_value, "invalid_date_format")
            )
            continue

        # 3) valor -> Decimal
        try:
            value = _normalize_decimal(raw_value)
        except (InvalidOperation, AttributeError):
            result.rejected.append(
                Rejection(series.series_id, raw_data, raw_value, "invalid_numeric_value")
            )
            continue

        # 4) limites de sanidade (por serie)
        if value < series.min_value or value > series.max_value:
            result.rejected.append(
                Rejection(series.series_id, raw_data, raw_value, "value_out_of_bounds")
            )
            continue

        # 5) duplicidade dentro do lote
        if reference_date in seen_dates:
            result.rejected.append(
                Rejection(series.series_id, raw_data, raw_value, "duplicate_in_batch")
            )
            continue
        seen_dates.add(reference_date)

        result.valid.append(
            {
                "series_id": series.series_id,
                "source": SOURCE,
                "reference_date": reference_date,
                "value": format(value, "f"),  # texto canonico, sem notacao cientifica
                "unit": series.unit,
                "collected_at": collected_at,
            }
        )

    logger.info(
        "%s: %d validos, %d rejeitados",
        series.series_id, len(result.valid), len(result.rejected),
    )
    return result
