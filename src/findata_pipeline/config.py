"""Configuracao central e registro de series.

Um modulo de configuracao dedicado (nao exigido pela estrutura base) se
justifica porque os metadados de cada serie - codigo SGS, unidade,
periodicidade e limites de sanidade - sao compartilhados pelo scraper e
pelo validator. Manter uma unica fonte de verdade evita duplicar essas
definicoes entre modulos e torna o validador "ciente da serie".
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

SOURCE = "BCB-SGS"
BASE_URL = os.environ.get(
    "DATA_SOURCE_BASE_URL",
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados",
)

# Raiz do projeto = dois niveis acima de src/findata_pipeline/config.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DB_PATH = os.environ.get("DB_PATH", str(PROJECT_ROOT / "data" / "findata.db"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "15"))
REPORTS_DIR = os.environ.get("REPORTS_DIR", str(PROJECT_ROOT / "reports"))

# --- API (v2) --------------------------------------------------------------
# Token opcional para proteger operacoes de escrita (POST /runs). Vazio =
# aberto (so aceitavel em ambiente estritamente local).
API_WRITE_TOKEN = os.environ.get("API_WRITE_TOKEN", "")
# Origens permitidas no CORS (lista separada por virgula); default: a origem
# local do dashboard Streamlit.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:8501").split(",")
    if origin.strip()
]
# Janela padrao (em dias) quando a API dispara uma coleta sem janela explicita.
DEFAULT_COLLECTION_DAYS = int(os.environ.get("DEFAULT_COLLECTION_DAYS", "180"))


@dataclass(frozen=True)
class SeriesConfig:
    """Metadados de uma serie temporal do SGS."""

    series_id: str          # identificador interno, ex. "BCB-SGS-12"
    sgs_code: int           # codigo da serie na API do BCB
    name: str               # nome legivel
    unit: str               # unidade do valor (importa para os limites)
    periodicity: str        # "business_day" | "calendar_day" | "monthly"
    min_value: Decimal      # limite inferior de sanidade
    max_value: Decimal      # limite superior de sanidade


# Series verificadas ao vivo contra a API SGS do BCB em 2026-10-28.
# Os limites refletem a unidade de cada serie: um valor plausivel para a
# CDI diaria (~0,04% a.d.) seria impossivel para a IPCA mensal, e vice-versa.
SERIES: dict[str, SeriesConfig] = {
    "BCB-SGS-12": SeriesConfig(
        series_id="BCB-SGS-12",
        sgs_code=12,
        name="CDI",
        unit="percent_per_day",
        periodicity="business_day",
        min_value=Decimal("0"),
        max_value=Decimal("5"),
    ),
    "BCB-SGS-432": SeriesConfig(
        series_id="BCB-SGS-432",
        sgs_code=432,
        name="Selic meta (Copom)",
        unit="percent_per_year",
        periodicity="calendar_day",
        min_value=Decimal("0"),
        max_value=Decimal("100"),
    ),
    "BCB-SGS-433": SeriesConfig(
        series_id="BCB-SGS-433",
        sgs_code=433,
        name="IPCA",
        unit="percent_per_month",
        periodicity="monthly",
        min_value=Decimal("-10"),
        max_value=Decimal("50"),
    ),
}
