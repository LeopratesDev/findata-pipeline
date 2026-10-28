"""Teste de contrato: verifica que a API real do BCB ainda entrega a
estrutura de que o pipeline depende.

DESLIGADO por padrao (precisa de --run-contract). Diferente da suite
offline, estes testes acessam a internet - o objetivo e detectar mudanca
de estrutura/descontinuacao da fonte ANTES que dado ruim entre no banco.

Se a API estiver indisponivel, o teste e pulado (skip), nao falha - assim
nao vira flaky; uma mudanca de estrutura, essa sim, faz falhar.
"""
from __future__ import annotations

import datetime

import pytest
import requests

from findata_pipeline.config import SERIES
from findata_pipeline.scraper import ScraperError, SgsClient
from findata_pipeline.validator import validate_records

pytestmark = pytest.mark.contract


@pytest.fixture(scope="module")
def client():
    return SgsClient(timeout=20)


@pytest.mark.parametrize("series_id", list(SERIES.keys()))
def test_series_structure_and_validation(client, series_id):
    series = SERIES[series_id]
    end = datetime.date.today()
    start = end - datetime.timedelta(days=400)  # janela larga: garante dado ate p/ serie mensal

    try:
        records = client.fetch_series(series, start=start, end=end)
    except (ScraperError, requests.RequestException) as exc:
        pytest.skip(f"API indisponivel: {exc}")

    # 1) estrutura: lista nao-vazia de registros com data/valor
    assert records, f"{series_id}: API retornou vazio numa janela de 400 dias"
    assert set(records[0]) >= {"series_id", "data", "valor"}

    # 2) contrato semantico: os dados reais ainda passam na nossa validacao
    result = validate_records(records, series)
    assert result.valid, f"{series_id}: nenhum registro valido"
    assert result.rejected == [], (
        f"{series_id}: {len(result.rejected)} rejeitados - formato ou faixa mudou?"
    )
