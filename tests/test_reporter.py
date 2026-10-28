"""Testes do reporter: agregacao com pandas, resumo e export JSON/CSV."""
from __future__ import annotations

import json

import pandas as pd

from findata_pipeline.reporter import ExecutionReport, SeriesOutcome


def _report():
    return ExecutionReport(
        source="BCB-SGS",
        started_at="2026-10-28T12:00:00Z",
        finished_at="2026-10-28T12:00:05Z",
        outcomes=[
            SeriesOutcome("BCB-SGS-12", extracted=3, valid=3, rejected=0, inserted=3),
            SeriesOutcome("BCB-SGS-433", extracted=2, valid=1, rejected=1, inserted=1),
        ],
    )


def test_totals_sum_across_series():
    totals = _report().totals()
    assert totals["extracted"] == 5
    assert totals["valid"] == 4
    assert totals["rejected"] == 1
    assert totals["inserted"] == 4


def test_dataframe_has_one_row_per_series():
    df = _report().to_dataframe()
    assert list(df["series_id"]) == ["BCB-SGS-12", "BCB-SGS-433"]
    assert len(df) == 2


def test_terminal_summary_contains_totals():
    text = _report().to_terminal()
    assert "Extraidos       : 5" in text
    assert "Validos         : 4" in text


def test_save_json_writes_totals_and_by_series(tmp_path):
    path = _report().save(str(tmp_path), fmt="json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["totals"]["valid"] == 4
    assert len(payload["by_series"]) == 2


def test_save_csv_is_readable_by_pandas(tmp_path):
    path = _report().save(str(tmp_path), fmt="csv")
    assert path.exists()
    df = pd.read_csv(path)
    assert len(df) == 2
    assert int(df["inserted"].sum()) == 4


def test_empty_report_has_zero_totals():
    report = ExecutionReport("BCB-SGS", "2026-10-28T12:00:00Z", "2026-10-28T12:00:01Z")
    assert report.totals() == {
        "extracted": 0, "valid": 0, "rejected": 0,
        "inserted": 0, "duplicates": 0, "revisions": 0,
    }
