"""Testes do scraper: extracao a partir de fixtures e tratamento de erros HTTP.

Nenhum teste depende de conexao real com a internet - um transporte falso
(FakeSession) substitui o requests.Session.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import requests

from findata_pipeline.config import SERIES
from findata_pipeline.scraper import (
    ScraperHTTPError,
    ScraperParseError,
    SgsClient,
    parse_sgs_json,
)

FIXTURES = Path(__file__).parent / "fixtures"
CDI = SERIES["BCB-SGS-12"]


class FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class FakeSession:
    """Session falsa: devolve uma resposta fixa ou levanta uma excecao."""

    def __init__(self, response=None, exc=None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[tuple] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if self._exc is not None:
            raise self._exc
        return self._response


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- parse_sgs_json (funcao pura) ---------------------------------------
def test_parse_valid_cdi_fixture():
    records = parse_sgs_json(_read("sgs_cdi_sample.json"), "BCB-SGS-12")
    assert len(records) == 3
    assert records[0] == {"series_id": "BCB-SGS-12", "data": "02/01/2024", "valor": "0.043739"}


def test_parse_rejects_html_error_page():
    with pytest.raises(ScraperParseError):
        parse_sgs_json(_read("sgs_error_page.html"), "BCB-SGS-12")


def test_parse_rejects_non_array_json():
    with pytest.raises(ScraperParseError):
        parse_sgs_json('{"erro": "serie invalida"}', "BCB-SGS-12")


def test_parse_rejects_record_missing_keys():
    with pytest.raises(ScraperParseError):
        parse_sgs_json('[{"data": "01/01/2024"}]', "BCB-SGS-12")


# --- SgsClient.fetch_series ---------------------------------------------
def test_fetch_series_success_builds_params_and_parses():
    from datetime import date

    session = FakeSession(FakeResponse(200, _read("sgs_cdi_sample.json")))
    client = SgsClient(session=session)
    records = client.fetch_series(CDI, start=date(2024, 1, 2), end=date(2024, 1, 4))

    assert len(records) == 3
    url, params, _ = session.calls[0]
    assert url.endswith("bcdata.sgs.12/dados")
    assert params["dataInicial"] == "02/01/2024"
    assert params["dataFinal"] == "04/01/2024"


def test_fetch_series_http_error_raises():
    session = FakeSession(FakeResponse(500, "erro interno"))
    client = SgsClient(session=session)
    with pytest.raises(ScraperHTTPError):
        client.fetch_series(CDI)


def test_fetch_series_connection_error_retries_then_raises():
    session = FakeSession(exc=requests.ConnectionError("sem rede"))
    client = SgsClient(session=session, max_retries=3, backoff_seconds=0)
    with pytest.raises(ScraperHTTPError):
        client.fetch_series(CDI)
    assert len(session.calls) == 3  # tentou 3 vezes antes de desistir
