"""Testes do adaptador de fonte HTML (BeautifulSoup).

Cobre extracao a partir de um fixture local, erros de estrutura e o
fluxo dos registros HTML pela validacao - sem acessar a internet.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from findata_pipeline.config import SeriesConfig
from findata_pipeline.html_source import HtmlTableClient, parse_html_table
from findata_pipeline.scraper import ScraperHTTPError, ScraperParseError
from findata_pipeline.validator import validate_records

FIXTURES = Path(__file__).parent / "fixtures"

# Serie de demonstracao para o adaptador HTML (nao faz parte do config de producao).
TESOURO = SeriesConfig(
    series_id="TESOURO-PRE-2027",
    sgs_code=0,
    name="Tesouro Prefixado 2027",
    unit="percent_per_year",
    periodicity="business_day",
    min_value=Decimal("0"),
    max_value=Decimal("100"),
)


class FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, response):
        self._response = response

    def get(self, url, timeout=None):
        return self._response


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_extracts_date_and_value():
    records = parse_html_table(
        _html("tesouro_sample.html"), "TESOURO-PRE-2027", "Data", "Taxa (% a.a.)"
    )
    assert len(records) == 3
    assert records[0] == {
        "series_id": "TESOURO-PRE-2027", "data": "02/01/2024", "valor": "10,53"
    }


def test_parse_missing_table_raises():
    with pytest.raises(ScraperParseError):
        parse_html_table("<html><body>sem tabela</body></html>", "X", "Data", "Taxa")


def test_parse_missing_headers_raises():
    html = "<table><tr><th>Coluna A</th><th>Coluna B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    with pytest.raises(ScraperParseError):
        parse_html_table(html, "X", "Data", "Taxa (% a.a.)")


def test_fetch_table_http_error_raises():
    client = HtmlTableClient(session=FakeSession(FakeResponse(500, "erro")))
    with pytest.raises(ScraperHTTPError):
        client.fetch_table("http://exemplo/x", "X", "Data", "Taxa (% a.a.)")


def test_html_records_flow_through_validator():
    records = parse_html_table(
        _html("tesouro_sample.html"), TESOURO.series_id, "Data", "Taxa (% a.a.)"
    )
    result = validate_records(records, TESOURO, collected_at="2026-10-28T12:00:00Z")
    assert result.rejected == []
    assert result.valid[0]["reference_date"] == "2024-01-02"   # dd/mm/yyyy -> ISO
    assert result.valid[0]["value"] == "10.53"                 # virgula -> ponto (Decimal)
