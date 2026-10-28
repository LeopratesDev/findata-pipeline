"""Cliente HTTP para a API de series temporais (SGS) do Banco Central.

Decisoes de projeto:
- ``parse_sgs_json`` e uma funcao pura (sem I/O), para que a logica de
  extracao possa ser testada contra fixtures locais, sem rede.
- ``SgsClient`` recebe uma ``requests.Session`` injetada, o que permite
  testar com um transporte falso e reaproveitar o pool de conexoes em
  producao.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Optional

import requests

from .config import BASE_URL, REQUEST_TIMEOUT, SeriesConfig

logger = logging.getLogger(__name__)

_DATE_FMT = "%d/%m/%Y"


class ScraperError(Exception):
    """Erro base do scraper."""


class ScraperHTTPError(ScraperError):
    """Status HTTP inesperado ou falha de conexao."""


class ScraperParseError(ScraperError):
    """Corpo da resposta nao e a estrutura JSON esperada."""


def parse_sgs_json(raw_text: str, series_id: str) -> list[dict]:
    """Converte o corpo JSON de uma resposta do SGS em registros brutos.

    Retorna uma lista de dicts ``{"series_id", "data", "valor"}``. Os
    valores sao mantidos como vieram (strings); a normalizacao acontece
    no validator. Estrutura inesperada gera erro explicito, nunca um
    resultado vazio silencioso.
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        # A API devolve uma pagina HTML de erro para algumas requisicoes
        # invalidas; isso aparece aqui como JSON invalido.
        raise ScraperParseError(
            f"resposta de {series_id} nao e JSON valido"
        ) from exc

    if not isinstance(payload, list):
        raise ScraperParseError(f"resposta de {series_id} nao e um array JSON")

    records: list[dict] = []
    for i, item in enumerate(payload):
        if not isinstance(item, dict) or "data" not in item or "valor" not in item:
            raise ScraperParseError(
                f"registro {i} de {series_id} sem 'data'/'valor'"
            )
        records.append(
            {"series_id": series_id, "data": item["data"], "valor": item["valor"]}
        )
    return records


class SgsClient:
    """Cliente simples para a API SGS, com timeout e retry com backoff."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: float = REQUEST_TIMEOUT,
        base_url: str = BASE_URL,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._session = session or requests.Session()
        self._timeout = timeout
        self._base_url = base_url
        self._max_retries = max_retries
        self._backoff = backoff_seconds

    def fetch_series(
        self,
        series: SeriesConfig,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> list[dict]:
        """Busca uma serie no SGS e retorna seus registros brutos."""
        url = self._base_url.format(code=series.sgs_code)
        params = {"formato": "json"}
        if start:
            params["dataInicial"] = start.strftime(_DATE_FMT)
        if end:
            params["dataFinal"] = end.strftime(_DATE_FMT)

        response = self._get_with_retry(url, params, series.series_id)

        if response.status_code != 200:
            raise ScraperHTTPError(
                f"{series.series_id}: status inesperado {response.status_code}"
            )

        records = parse_sgs_json(response.text, series.series_id)
        logger.info("coletados %d registros brutos de %s", len(records), series.series_id)
        return records

    def _get_with_retry(self, url: str, params: dict, series_id: str):
        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "erro de conexao em %s (tentativa %d/%d): %s",
                    series_id, attempt, self._max_retries, exc,
                )
                if attempt < self._max_retries:
                    time.sleep(self._backoff * attempt)
        raise ScraperHTTPError(
            f"{series_id}: conexao falhou apos {self._max_retries} tentativas"
        ) from last_exc
