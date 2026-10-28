"""Avaliacao de alertas pos-execucao.

Regras acionaveis por quem opera a rotina de coleta:
- erro de coleta em qualquer serie  -> alerta de severidade 'error';
- taxa de rejeicao acima do limite  -> 'warning';
- nenhum registro extraido (sem erro de coleta) -> 'warning'.

O canal padrao de alerta e o log. Integracoes externas (webhook, e-mail)
ficam como extensao e NAO estao implementadas aqui - nao se envia nada para
fora por padrao.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from .reporter import ExecutionReport

logger = logging.getLogger(__name__)

DEFAULT_MAX_REJECTION_RATE = 0.2  # 20%


@dataclass
class Alert:
    severity: str   # "error" | "warning"
    code: str
    message: str


def evaluate(
    report: ExecutionReport, max_rejection_rate: float = DEFAULT_MAX_REJECTION_RATE
) -> list[Alert]:
    """Deriva a lista de alertas a partir do relatorio de execucao."""
    alerts: list[Alert] = []

    for err in report.errors:
        alerts.append(Alert("error", "collection_failed", err))

    # series que ja falharam na coleta ("BCB-SGS-12: ..." -> "BCB-SGS-12")
    errored = {err.split(":", 1)[0] for err in report.errors}

    for outcome in report.outcomes:
        if outcome.series_id in errored:
            continue  # ja alertado pela falha de coleta
        if outcome.extracted == 0:
            alerts.append(
                Alert("warning", "no_data", f"{outcome.series_id}: nenhum registro extraido")
            )
            continue
        rate = outcome.rejected / outcome.extracted
        if rate > max_rejection_rate:
            alerts.append(
                Alert(
                    "warning",
                    "high_rejection_rate",
                    f"{outcome.series_id}: taxa de rejeicao {rate:.0%} "
                    f"acima do limite {max_rejection_rate:.0%}",
                )
            )
    return alerts


# Idade maxima aceitavel do ultimo dado, por periodicidade (dias).
PERIODICITY_MAX_AGE_DAYS = {"business_day": 5, "calendar_day": 5, "monthly": 40}


def evaluate_freshness(
    latest: dict, today: date, max_age_days: dict | None = None
) -> list[Alert]:
    """Alerta 'stale_data' quando a ultima data de uma serie esta mais velha
    que o limite da sua periodicidade. `latest` mapeia series_id ->
    {"reference_date": "YYYY-MM-DD", "periodicity": "..."}."""
    max_age_days = max_age_days or PERIODICITY_MAX_AGE_DAYS
    alerts: list[Alert] = []
    for series_id, info in latest.items():
        reference_date = info.get("reference_date")
        if not reference_date:
            continue
        try:
            age = (today - date.fromisoformat(reference_date)).days
        except ValueError:
            continue
        limit = max_age_days.get(info.get("periodicity"), 30)
        if age > limit:
            alerts.append(
                Alert("warning", "stale_data",
                      f"{series_id}: ultimo dado ha {age} dias (limite {limit})")
            )
    return alerts


def emit(alerts: list[Alert]) -> int:
    """Escreve os alertas no log (canal padrao). Retorna quantos dispararam."""
    for alert in alerts:
        log = logger.error if alert.severity == "error" else logger.warning
        log("ALERTA [%s] %s", alert.code, alert.message)
    return len(alerts)
