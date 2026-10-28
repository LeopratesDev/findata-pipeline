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


def emit(alerts: list[Alert]) -> int:
    """Escreve os alertas no log (canal padrao). Retorna quantos dispararam."""
    for alert in alerts:
        log = logger.error if alert.severity == "error" else logger.warning
        log("ALERTA [%s] %s", alert.code, alert.message)
    return len(alerts)
