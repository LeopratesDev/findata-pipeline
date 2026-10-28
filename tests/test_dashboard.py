"""Testes das funcoes puras do dashboard: cliente da API e formatacao.

Sem rede e sem UI: o cliente usa um transporte falso; a importacao do app
Streamlit e checada sem executar a interface (guardada por __main__).
"""
from __future__ import annotations

import importlib

import pytest

from findata_pipeline.dashboard import format as fmt
from findata_pipeline.dashboard.client import ApiClient, ApiError


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("sem json")
        return self._json


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        return self.response

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers))
        return self.response


# --- cliente ----------------------------------------------------------------
def test_get_latest_parses_json():
    session = FakeSession(FakeResponse(200, {"series_id": "BCB-SGS-12", "has_data": True}))
    client = ApiClient("http://api", session=session)
    assert client.get_latest("BCB-SGS-12")["has_data"] is True
    assert session.calls[-1][1] == "http://api/api/v1/indicators/BCB-SGS-12/latest"


def test_get_history_sends_filters_and_pagination():
    session = FakeSession(FakeResponse(200, {"items": []}))
    client = ApiClient("http://api", session=session)
    client.get_history("BCB-SGS-12", start="2024-01-01", end="2024-02-01", limit=10, include_history=True)
    params = session.calls[-1][2]
    assert params["limit"] == 10
    assert params["offset"] == 0
    assert params["include_history"] == "true"
    assert params["start"] == "2024-01-01" and params["end"] == "2024-02-01"


def test_http_error_becomes_apierror():
    session = FakeSession(FakeResponse(404, {"detail": "serie desconhecida"}))
    client = ApiClient("http://api", session=session)
    with pytest.raises(ApiError) as exc:
        client.get_latest("X")
    assert exc.value.status_code == 404
    assert exc.value.detail == "serie desconhecida"


def test_health_ok_false_on_error():
    client = ApiClient("http://api", session=FakeSession(FakeResponse(500, {"detail": "boom"})))
    assert client.health_ok() is False


def test_create_run_sends_token_and_body():
    session = FakeSession(FakeResponse(202, {"run_id": 1, "status": "running"}))
    client = ApiClient("http://api", session=session, token="segredo")
    client.create_run(days=90)
    method, url, body, headers = session.calls[-1]
    assert method == "POST" and url == "http://api/api/v1/runs"
    assert body == {"days": 90}
    assert headers["X-API-Token"] == "segredo"


# --- formatacao -------------------------------------------------------------
def test_format_date_br():
    assert fmt.format_date("2024-01-02") == "02/01/2024"
    assert fmt.format_date(None) == ""


def test_format_datetime_br():
    assert fmt.format_datetime("2026-10-28T14:54:37Z") == "28/10/2026 14:54"


def test_format_value_keeps_precision_as_string():
    # nao vira float: preserva as casas e so troca ponto por virgula
    assert fmt.format_value("0.040168", "percent_per_day") == "0,040168 % a.d."
    assert fmt.format_value(None) == "—"


def test_unit_label_maps_known_units():
    assert fmt.unit_label("percent_per_year") == "% a.a."
    assert fmt.unit_label("percent_per_month") == "% a.m."


def test_status_label_pt_br():
    assert fmt.status_label("done") == "Concluida"
    assert fmt.status_category("failed") == "error"


def test_format_duration():
    assert fmt.format_duration(5) == "5 s"
    assert fmt.format_duration(63) == "1 min 3 s"
    assert fmt.format_duration(None) == "—"


def test_history_to_chart_sorts_ascending_and_floats():
    items = [
        {"reference_date": "2024-01-03", "value": "0.05"},
        {"reference_date": "2024-01-02", "value": "0.04"},
    ]
    chart = fmt.history_to_chart(items)
    assert chart["dates"] == ["2024-01-02", "2024-01-03"]
    assert chart["values"] == [0.04, 0.05]


def test_history_to_chart_skips_invalid_values():
    items = [{"reference_date": "2024-01-02", "value": "abc"}]
    assert fmt.history_to_chart(items) == {"dates": [], "values": []}


def test_moving_average_trailing_with_leading_nones():
    assert fmt.moving_average([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert fmt.moving_average([10, 20], 1) == [10, 20]  # janela 1 = sem suavizar


# --- importacao da UI (sem executar a interface) ----------------------------
def test_dashboard_app_imports_cleanly():
    module = importlib.import_module("findata_pipeline.dashboard.app")
    assert hasattr(module, "render")
