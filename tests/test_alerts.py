"""Testes da avaliacao de alertas pos-execucao."""
from __future__ import annotations

from datetime import date

from findata_pipeline.alerts import evaluate, evaluate_freshness
from findata_pipeline.reporter import ExecutionReport, SeriesOutcome


def _report(outcomes, errors=None):
    return ExecutionReport(
        source="BCB-SGS",
        started_at="2026-10-28T12:00:00Z",
        finished_at="2026-10-28T12:00:05Z",
        outcomes=outcomes,
        errors=errors or [],
    )


def test_no_alerts_on_clean_run():
    report = _report([SeriesOutcome("BCB-SGS-12", extracted=10, valid=10, rejected=0)])
    assert evaluate(report) == []


def test_collection_error_raises_error_alert():
    report = _report(
        [SeriesOutcome("BCB-SGS-12", extracted=0)],
        errors=["BCB-SGS-12: coleta falhou: status 500"],
    )
    alerts = evaluate(report)
    # apenas o alerta de erro; o extracted=0 nao gera 'no_data' pois ja houve erro
    assert len(alerts) == 1
    assert alerts[0].severity == "error"
    assert alerts[0].code == "collection_failed"


def test_high_rejection_rate_raises_warning():
    report = _report([SeriesOutcome("BCB-SGS-433", extracted=10, valid=6, rejected=4)])  # 40%
    alerts = evaluate(report, max_rejection_rate=0.2)
    assert len(alerts) == 1
    assert alerts[0].code == "high_rejection_rate"
    assert alerts[0].severity == "warning"


def test_rejection_rate_within_limit_is_silent():
    report = _report([SeriesOutcome("BCB-SGS-433", extracted=10, valid=9, rejected=1)])  # 10%
    assert evaluate(report, max_rejection_rate=0.2) == []


def test_zero_extracted_without_error_raises_no_data():
    report = _report([SeriesOutcome("BCB-SGS-12", extracted=0)])
    alerts = evaluate(report)
    assert len(alerts) == 1
    assert alerts[0].code == "no_data"


def test_evaluate_freshness_flags_stale_series():
    today = date(2026, 10, 28)
    latest = {
        "BCB-SGS-12": {"reference_date": "2026-10-27", "periodicity": "business_day"},   # fresco
        "BCB-SGS-433": {"reference_date": "2026-06-01", "periodicity": "monthly"},        # velho
    }
    found = evaluate_freshness(latest, today)
    assert len(found) == 1
    assert found[0].code == "stale_data"
    assert "BCB-SGS-433" in found[0].message
