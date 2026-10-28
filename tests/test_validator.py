"""Testes do validator: normalizacao, conversoes e motivos de rejeicao."""
from __future__ import annotations

from findata_pipeline.config import SERIES
from findata_pipeline.validator import validate_records

CDI = SERIES["BCB-SGS-12"]
COLLECTED_AT = "2026-10-28T12:00:00Z"


def _rec(data, valor):
    return {"series_id": CDI.series_id, "data": data, "valor": valor}


def test_valid_record_is_normalized():
    result = validate_records([_rec("02/01/2024", "0.043739")], CDI, COLLECTED_AT)
    assert not result.rejected
    obs = result.valid[0]
    assert obs["reference_date"] == "2024-01-02"      # dd/MM/yyyy -> ISO 8601
    assert obs["value"] == "0.043739"                 # precisao preservada
    assert obs["unit"] == "percent_per_day"
    assert obs["source"] == "BCB-SGS"
    assert obs["collected_at"] == COLLECTED_AT


def test_rejects_missing_value():
    result = validate_records([_rec("02/01/2024", "")], CDI, COLLECTED_AT)
    assert result.valid == []
    assert result.rejected[0].reason == "missing_required_field"


def test_rejects_invalid_date_format():
    # ISO em vez de dd/MM/yyyy deve ser rejeitado pelo parser estrito.
    result = validate_records([_rec("2024-01-02", "0.04")], CDI, COLLECTED_AT)
    assert result.rejected[0].reason == "invalid_date_format"


def test_rejects_non_numeric_value():
    result = validate_records([_rec("02/01/2024", "abc")], CDI, COLLECTED_AT)
    assert result.rejected[0].reason == "invalid_numeric_value"


def test_rejects_value_out_of_bounds():
    # 9% ao dia e impossivel para a CDI (limite max = 5).
    result = validate_records([_rec("02/01/2024", "9")], CDI, COLLECTED_AT)
    assert result.rejected[0].reason == "value_out_of_bounds"


def test_detects_duplicate_within_batch():
    batch = [_rec("02/01/2024", "0.04"), _rec("02/01/2024", "0.04")]
    result = validate_records(batch, CDI, COLLECTED_AT)
    assert len(result.valid) == 1
    assert result.rejected[0].reason == "duplicate_in_batch"


def test_accepts_comma_decimal_defensively():
    result = validate_records([_rec("02/01/2024", "0,04")], CDI, COLLECTED_AT)
    assert result.valid[0]["value"] == "0.04"
