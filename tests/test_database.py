"""Testes do database: persistencia, idempotencia, revisao e auditoria."""
from __future__ import annotations

import pytest

from findata_pipeline.database import Database, WriteStats
from findata_pipeline.validator import Rejection

COLLECTED_AT = "2026-10-28T12:00:00Z"


def _obs(reference_date: str, value: str):
    return {
        "series_id": "BCB-SGS-12",
        "source": "BCB-SGS",
        "reference_date": reference_date,
        "value": value,
        "unit": "percent_per_day",
        "collected_at": COLLECTED_AT,
    }


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    database.initialize()
    yield database
    database.close()


def test_insert_and_query(db):
    db.insert_observations([_obs("2024-01-02", "0.04"), _obs("2024-01-03", "0.04")])
    rows = db.get_observations("BCB-SGS-12")
    assert [r["reference_date"] for r in rows] == ["2024-01-02", "2024-01-03"]
    assert db.count_observations() == 2


def test_idempotency_no_duplicates_on_rerun(db):
    batch = [_obs("2024-01-02", "0.04"), _obs("2024-01-03", "0.04")]
    first = db.insert_observations(batch)
    second = db.insert_observations(batch)  # mesma coleta de novo

    assert first == WriteStats(inserted=2, duplicates=0, revisions=0)
    assert second == WriteStats(inserted=0, duplicates=2, revisions=0)
    assert db.count_observations() == 2  # nada duplicou


def test_revision_keeps_history_and_updates_current(db):
    db.insert_observations([_obs("2024-01-02", "0.04")])
    stats = db.insert_observations([_obs("2024-01-02", "0.05")])  # valor revisado

    assert stats.revisions == 1

    current = db.get_observations("BCB-SGS-12")
    assert len(current) == 1
    assert current[0]["value"] == "0.05"   # atual = valor revisado
    assert current[0]["version"] == 2

    history = db.get_history("BCB-SGS-12", "2024-01-02")
    assert [h["value"] for h in history] == ["0.04", "0.05"]   # historico preservado
    assert history[0]["is_current"] == 0 and history[0]["superseded_at"] is not None
    assert history[1]["is_current"] == 1 and history[1]["superseded_at"] is None

    assert db.count_observations() == 1    # apenas uma versao atual


def test_rerun_after_revision_is_idempotent(db):
    db.insert_observations([_obs("2024-01-02", "0.04")])
    db.insert_observations([_obs("2024-01-02", "0.05")])
    again = db.insert_observations([_obs("2024-01-02", "0.05")])  # mesmo valor atual

    assert again == WriteStats(inserted=0, duplicates=1, revisions=0)
    assert len(db.get_history("BCB-SGS-12", "2024-01-02")) == 2   # nenhuma versao nova


def test_get_observations_excludes_history_by_default(db):
    db.insert_observations([_obs("2024-01-02", "0.04")])
    db.insert_observations([_obs("2024-01-02", "0.05")])

    assert len(db.get_observations("BCB-SGS-12")) == 1                      # so atual
    assert len(db.get_observations("BCB-SGS-12", include_history=True)) == 2  # com historico


def test_rejections_are_persisted(db):
    rejections = [
        Rejection("BCB-SGS-12", "99/99/2024", "0.04", "invalid_date_format"),
        Rejection("BCB-SGS-12", "02/01/2024", "abc", "invalid_numeric_value"),
    ]
    count = db.insert_rejections(run_id=1, rejections=rejections, collected_at=COLLECTED_AT)
    assert count == 2


def test_run_lifecycle(db):
    run_id = db.start_run("BCB-SGS", "2026-10-28T12:00:00Z")
    db.finish_run(
        run_id, "2026-10-28T12:00:05Z",
        extracted=3, valid=3, rejected=0,
        stats=WriteStats(inserted=3), status="done",
    )
    # start_run deve devolver um id valido e finish_run nao deve falhar.
    assert isinstance(run_id, int) and run_id >= 1
