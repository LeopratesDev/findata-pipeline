"""Formatacao pura para o dashboard (datas pt-BR, unidades, grafico).

Nao converte Decimal em float na camada de negocio: os valores vem da API
como string e aqui so trocamos o ponto por virgula para exibir. A conversao
para float acontece apenas para plotagem (history_to_chart), nunca para
calculo ou persistencia.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

UNIT_LABELS = {
    "percent_per_day": "% a.d.",
    "percent_per_year": "% a.a.",
    "percent_per_month": "% a.m.",
}

STATUS_LABELS = {
    "done": ("Concluida", "success"),
    "completed_with_errors": ("Concluida com erros", "warning"),
    "running": ("Em execucao", "info"),
    "failed": ("Falhou", "error"),
}


def unit_label(unit: Optional[str]) -> str:
    return UNIT_LABELS.get(unit, unit or "")


def format_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso


def format_datetime(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return iso


def parse_value(value_str) -> Optional[Decimal]:
    try:
        return Decimal(str(value_str))
    except (InvalidOperation, TypeError, ValueError):
        return None


def format_value(value_str, unit: Optional[str] = None) -> str:
    """Valor para exibicao: preserva o texto (nao vira float), troca ponto
    por virgula e anexa a unidade. None -> travessao."""
    if value_str is None:
        return "—"
    text = str(value_str).replace(".", ",")
    label = unit_label(unit) if unit else ""
    return f"{text} {label}".strip()


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    return f"{minutes} min {rest} s"


def status_label(status: Optional[str]) -> str:
    return STATUS_LABELS.get(status, (status or "—", "info"))[0]


def status_category(status: Optional[str]) -> str:
    return STATUS_LABELS.get(status, ("", "info"))[1]


def history_to_chart(items: list[dict]) -> dict:
    """Converte items (vindos mais recente -> mais antigo) numa serie
    ascendente por data para plotagem. Floats apenas para o grafico;
    registros sem valor numerico sao ignorados."""
    pairs = []
    for item in items:
        value = parse_value(item.get("value"))
        if value is None:
            continue
        pairs.append((item.get("reference_date"), float(value)))
    pairs.sort(key=lambda pair: pair[0] or "")
    return {"dates": [p[0] for p in pairs], "values": [p[1] for p in pairs]}
