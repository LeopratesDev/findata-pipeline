"""Configuracao do pytest compartilhada.

Os testes marcados com @pytest.mark.contract acessam a API real do BCB e
ficam DESLIGADOS por padrao - a suite normal roda offline. Para executa-los:

    pytest -m contract --run-contract
"""
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-contract",
        action="store_true",
        default=False,
        help="roda os testes de contrato (acessam a API real do BCB, exigem internet)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "contract: teste que acessa a API real do BCB (requer --run-contract)"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-contract"):
        return
    skip = pytest.mark.skip(reason="precisa de --run-contract (acessa a internet)")
    for item in items:
        if "contract" in item.keywords:
            item.add_marker(skip)
