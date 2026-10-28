"""Testes da API REST (FastAPI) - sem rede.

A coleta real e substituida por um SgsClient com transporte falso; o
executor da tarefa em background pode ser inline (roda na hora) ou diferido
(para testar o conflito 409).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from findata_pipeline.api.app import create_app
from findata_pipeline.api.runner import PipelineRunner
from findata_pipeline.database import Database, WriteStats
from findata_pipeline.scraper import SgsClient

CDI_JSON = '[{"data":"02/01/2024","valor":"0.043739"},{"data":"03/01/2024","valor":"0.043739"},{"data":"04/01/2024","valor":"0.041680"}]'
SELIC_JSON = '[{"data":"02/01/2024","valor":"11.75"}]'
IPCA_JSON = '[{"data":"01/01/2024","valor":"0.42"},{"data":"01/02/2024","valor":"0.83"}]'


# --- duble de rede e de executor -------------------------------------------
class FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class MultiFakeSession:
    def __init__(self, by_code):
        self.by_code = by_code

    def get(self, url, params=None, timeout=None):
        code = int(re.search(r"sgs\.(\d+)/dados", url).group(1))
        status, text = self.by_code[code]
        return FakeResponse(status, text)


def fake_client_factory():
    return SgsClient(
        session=MultiFakeSession({12: (200, CDI_JSON), 432: (200, SELIC_JSON), 433: (200, IPCA_JSON)})
    )


class InlineExecutor:
    """Roda a tarefa imediatamente (sincrono), para testar o caminho feliz."""

    def submit(self, fn, *args):
        fn(*args)
        return None


class DeferredExecutor:
    """Guarda a tarefa sem rodar, para manter o lock preso (testar 409)."""

    def __init__(self):
        self.tasks = []

    def submit(self, fn, *args):
        self.tasks.append((fn, args))
        return None


# --- fixtures ---------------------------------------------------------------
def _seed(db: Database):
    db.insert_observations([
        {"series_id": "BCB-SGS-12", "source": "BCB-SGS", "reference_date": "2024-01-02",
         "value": "0.040168", "unit": "percent_per_day", "collected_at": "2026-10-28T12:00:00Z"},
        {"series_id": "BCB-SGS-12", "source": "BCB-SGS", "reference_date": "2024-01-03",
         "value": "0.040168", "unit": "percent_per_day", "collected_at": "2026-10-28T12:00:00Z"},
        {"series_id": "BCB-SGS-433", "source": "BCB-SGS", "reference_date": "2024-01-01",
         "value": "0.42", "unit": "percent_per_month", "collected_at": "2026-10-28T12:00:00Z"},
    ])
    rid = db.start_run("BCB-SGS", "2026-10-28T12:00:00Z", trigger="cli")
    db.finish_run(rid, "2026-10-28T12:00:05Z", extracted=3, valid=3, rejected=0,
                  stats=WriteStats(inserted=3), status="done")
    db.insert_rejections(rid, [], "2026-10-28T12:00:00Z")


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "api.db")
    db = Database(path)
    db.initialize()
    _seed(db)
    db.close()
    return path


def build_client(db_path, runner=None, write_token="") -> TestClient:
    app = create_app(db_path=db_path, runner=runner, write_token=write_token, cors_origins=["*"])
    return TestClient(app)


@pytest.fixture()
def client(db_path):
    return build_client(db_path)


# --- saude e status ---------------------------------------------------------
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_ready_ok(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_status_summary(client):
    r = client.get("/api/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert body["observations_count"] == 3
    assert body["indicators"] == 3
    assert body["last_run"]["status"] == "done"


# --- indicadores ------------------------------------------------------------
def test_list_indicators(client):
    r = client.get("/api/v1/indicators")
    assert r.status_code == 200
    ids = {i["series_id"]: i for i in r.json()}
    assert set(ids) == {"BCB-SGS-12", "BCB-SGS-432", "BCB-SGS-433"}
    assert ids["BCB-SGS-12"]["unit"] == "percent_per_day"


def test_latest_returns_string_value(client):
    r = client.get("/api/v1/indicators/BCB-SGS-12/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["has_data"] is True
    assert body["observation"]["reference_date"] == "2024-01-03"
    assert isinstance(body["observation"]["value"], str)  # decimal como string


def test_latest_unknown_series_404(client):
    r = client.get("/api/v1/indicators/BCB-SGS-999/latest")
    assert r.status_code == 404


def test_latest_known_series_without_data(client):
    # Selic existe no registro mas nao foi semeada
    r = client.get("/api/v1/indicators/BCB-SGS-432/latest")
    assert r.status_code == 200
    assert r.json()["has_data"] is False


def test_history_pagination(client):
    r = client.get("/api/v1/indicators/BCB-SGS-12/history", params={"limit": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["count"] == 1
    assert len(body["items"]) == 1


def test_history_invalid_date_422(client):
    r = client.get("/api/v1/indicators/BCB-SGS-12/history", params={"start": "nao-e-data"})
    assert r.status_code == 422


def test_history_limit_out_of_range_422(client):
    r = client.get("/api/v1/indicators/BCB-SGS-12/history", params={"limit": 0})
    assert r.status_code == 422


# --- execucoes --------------------------------------------------------------
def test_list_runs(client):
    r = client.get("/api/v1/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert body["items"][0]["status"] == "done"


def test_run_detail_includes_rejections(client):
    run_id = client.get("/api/v1/runs").json()["items"][0]["id"]
    r = client.get(f"/api/v1/runs/{run_id}")
    assert r.status_code == 200
    assert "rejections" in r.json()


def test_run_detail_404(client):
    assert client.get("/api/v1/runs/9999").status_code == 404


def test_create_run_202_and_completes(db_path):
    runner = PipelineRunner(db_path, client_factory=fake_client_factory, executor=InlineExecutor())
    client = build_client(db_path, runner=runner)

    before = client.get("/api/v1/status").json()["observations_count"]
    r = client.post("/api/v1/runs", json={"days": 120})
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    status = client.get(f"/api/v1/runs/{run_id}/status").json()
    assert status["status"] in {"done", "completed_with_errors"}

    after = client.get("/api/v1/status").json()["observations_count"]
    assert after >= before
    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["trigger"] == "api"


def test_create_run_conflict_409(db_path):
    runner = PipelineRunner(db_path, client_factory=fake_client_factory, executor=DeferredExecutor())
    client = build_client(db_path, runner=runner)

    first = client.post("/api/v1/runs", json={})
    assert first.status_code == 202
    second = client.post("/api/v1/runs", json={})  # tarefa anterior nao terminou
    assert second.status_code == 409


def test_create_run_requires_token_when_configured(db_path):
    runner = PipelineRunner(db_path, client_factory=fake_client_factory, executor=InlineExecutor())
    client = build_client(db_path, runner=runner, write_token="segredo")

    assert client.post("/api/v1/runs", json={}).status_code == 401
    ok = client.post("/api/v1/runs", json={}, headers={"X-API-Token": "segredo"})
    assert ok.status_code == 202


def test_create_run_invalid_series_422(client):
    r = client.post("/api/v1/runs", json={"series_ids": ["BCB-SGS-999"]})
    assert r.status_code == 422


# --- relatorios -------------------------------------------------------------
def test_reports_list_and_download(client, tmp_path, monkeypatch):
    import findata_pipeline.config as cfg
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "report_x.json").write_text('{"ok": true}', encoding="utf-8")
    monkeypatch.setattr(cfg, "REPORTS_DIR", str(reports_dir))

    listing = client.get("/api/v1/reports")
    assert listing.status_code == 200
    assert any(r["report_id"] == "report_x.json" for r in listing.json())

    dl = client.get("/api/v1/reports/report_x.json/download")
    assert dl.status_code == 200
    assert dl.json() == {"ok": True}


def test_report_download_missing_404(client, tmp_path, monkeypatch):
    import findata_pipeline.config as cfg
    monkeypatch.setattr(cfg, "REPORTS_DIR", str(tmp_path))
    assert client.get("/api/v1/reports/report_inexistente.json/download").status_code == 404


def test_report_download_bad_suffix_400(client, tmp_path, monkeypatch):
    import findata_pipeline.config as cfg
    monkeypatch.setattr(cfg, "REPORTS_DIR", str(tmp_path))
    # extensao fora da lista permitida
    assert client.get("/api/v1/reports/notas.txt/download").status_code == 400


def test_resolve_report_path_blocks_traversal(tmp_path, monkeypatch):
    import findata_pipeline.config as cfg
    from findata_pipeline.api import services
    monkeypatch.setattr(cfg, "REPORTS_DIR", str(tmp_path))
    with pytest.raises(services.InvalidReportIdError):
        services.resolve_report_path("../../etc/passwd.json")
