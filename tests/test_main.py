"""Testes de integracao do pipeline (run_pipeline) com transporte falso.

Cobre o fluxo ponta-a-ponta sem rede: coleta (fake) -> validacao ->
persistencia -> relatorio, incluindo idempotencia end-to-end e o
tratamento de falha de coleta em uma serie sem derrubar as demais.
"""
from __future__ import annotations

import re

import pytest

from findata_pipeline.database import Database
from findata_pipeline.main import run_pipeline
from findata_pipeline.scraper import SgsClient

CDI_JSON = '[{"data":"02/01/2024","valor":"0.043739"},{"data":"03/01/2024","valor":"0.043739"},{"data":"04/01/2024","valor":"0.041680"}]'
SELIC_JSON = '[{"data":"02/01/2024","valor":"11.75"}]'
IPCA_JSON = '[{"data":"01/01/2024","valor":"0.42"},{"data":"01/02/2024","valor":"0.83"}]'


class FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class MultiFakeSession:
    """Devolve uma resposta por codigo de serie, lida da URL."""

    def __init__(self, by_code: dict):
        self.by_code = by_code

    def get(self, url, params=None, timeout=None):
        code = int(re.search(r"sgs\.(\d+)/dados", url).group(1))
        status, text = self.by_code[code]
        return FakeResponse(status, text)


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "pipeline.db"))
    database.initialize()
    yield database
    database.close()


def _all_ok_session():
    return MultiFakeSession({
        12: (200, CDI_JSON),
        432: (200, SELIC_JSON),
        433: (200, IPCA_JSON),
    })


def test_pipeline_persists_all_valid_records(db):
    client = SgsClient(session=_all_ok_session())
    report = run_pipeline(client, db)

    assert report.totals()["valid"] == 6      # 3 + 1 + 2
    assert report.totals()["inserted"] == 6
    assert db.count_observations() == 6
    assert report.errors == []


def test_pipeline_is_idempotent_end_to_end(db):
    client = SgsClient(session=_all_ok_session())
    run_pipeline(client, db)
    second = run_pipeline(client, db)  # mesma coleta de novo

    assert second.totals()["inserted"] == 0
    assert second.totals()["duplicates"] == 6
    assert db.count_observations() == 6    # nada duplicou


def test_pipeline_records_error_for_one_series_and_continues(db):
    session = MultiFakeSession({
        12: (500, "erro interno"),     # CDI falha
        432: (200, SELIC_JSON),
        433: (200, IPCA_JSON),
    })
    report = run_pipeline(SgsClient(session=session), db)

    assert len(report.errors) == 1
    assert "BCB-SGS-12" in report.errors[0]
    assert db.count_observations() == 3    # Selic (1) + IPCA (2) persistiram
