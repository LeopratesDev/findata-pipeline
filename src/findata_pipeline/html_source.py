"""Adaptador de fonte HTML usando BeautifulSoup.

A fonte principal do projeto e a API JSON do BCB. Este adaptador existe
para fontes que publicam os dados numa TABELA HTML: le uma tabela, extrai
as colunas de data e valor pelos cabecalhos e devolve registros no MESMO
formato do scraper do SGS ({series_id, data, valor}), de modo que o
validator e o database funcionem sem qualquer alteracao.

NOTA DE HONESTIDADE: a pagina real do Tesouro Nacional (Oracle APEX) e
renderizada via JavaScript; requests + BeautifulSoup NAO conseguem extrair
seus dados (precisaria de um navegador headless). Por isso este adaptador e
demonstrado contra um fixture HTML representativo (claramente dado de teste)
e serve para qualquer fonte que publique uma tabela HTML estatica.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .config import REQUEST_TIMEOUT
from .scraper import ScraperHTTPError, ScraperParseError

logger = logging.getLogger(__name__)


def parse_html_table(
    html: str,
    series_id: str,
    date_header: str,
    value_header: str,
    table_selector: Optional[str] = None,
) -> list[dict]:
    """Extrai registros (data, valor) de uma tabela HTML.

    As colunas sao localizadas pelos textos de cabecalho ``date_header`` e
    ``value_header``; ``table_selector`` (CSS) escolhe a tabela quando ha
    mais de uma. Os valores sao mantidos como texto (a normalizacao e a
    conversao decimal acontecem no validator).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(table_selector) if table_selector else soup.find("table")
    if table is None:
        raise ScraperParseError(f"{series_id}: nenhuma tabela encontrada no HTML")

    headers = [cell.get_text(strip=True) for cell in table.find_all("th")]
    if not headers:  # fallback: primeira linha como cabecalho
        first_row = table.find("tr")
        headers = (
            [c.get_text(strip=True) for c in first_row.find_all(["td", "th"])]
            if first_row else []
        )
    try:
        date_idx = headers.index(date_header)
        value_idx = headers.index(value_header)
    except ValueError as exc:
        raise ScraperParseError(
            f"{series_id}: cabecalhos '{date_header}'/'{value_header}' "
            f"nao encontrados em {headers}"
        ) from exc

    records: list[dict] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) <= max(date_idx, value_idx):
            continue  # linha de cabecalho ou incompleta
        records.append(
            {
                "series_id": series_id,
                "data": cells[date_idx].get_text(strip=True),
                "valor": cells[value_idx].get_text(strip=True),
            }
        )
    logger.info("extraidos %d registros de tabela HTML para %s", len(records), series_id)
    return records


class HtmlTableClient:
    """Busca uma pagina HTML e extrai uma tabela como registros."""

    def __init__(
        self, session: Optional[requests.Session] = None, timeout: float = REQUEST_TIMEOUT
    ) -> None:
        self._session = session or requests.Session()
        self._timeout = timeout

    def fetch_table(
        self,
        url: str,
        series_id: str,
        date_header: str,
        value_header: str,
        table_selector: Optional[str] = None,
    ) -> list[dict]:
        try:
            response = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as exc:
            raise ScraperHTTPError(f"{series_id}: falha de conexao: {exc}") from exc
        if response.status_code != 200:
            raise ScraperHTTPError(
                f"{series_id}: status inesperado {response.status_code}"
            )
        return parse_html_table(
            response.text, series_id, date_header, value_header, table_selector
        )
