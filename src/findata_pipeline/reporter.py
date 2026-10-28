"""Relatorio de execucao: estatisticas por serie, resumo no terminal e export.

Usa pandas para agregar as contagens por serie - um uso genuino, ja que a
tabela resultante vira CSV e facilita a leitura/soma. O relatorio pode ser
exportado em JSON ou CSV; o resumo no terminal e sempre montado aqui e
impresso pelo main.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_NUMERIC_COLUMNS = ["extracted", "valid", "rejected", "inserted", "duplicates", "revisions"]


@dataclass
class SeriesOutcome:
    """Resultado da execucao para uma unica serie."""

    series_id: str
    extracted: int = 0
    valid: int = 0
    rejected: int = 0
    inserted: int = 0
    duplicates: int = 0
    revisions: int = 0


@dataclass
class ExecutionReport:
    source: str
    started_at: str
    finished_at: str
    outcomes: list[SeriesOutcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.outcomes:
            return pd.DataFrame(columns=["series_id", *_NUMERIC_COLUMNS])
        return pd.DataFrame([asdict(o) for o in self.outcomes])

    def totals(self) -> dict:
        df = self.to_dataframe()
        if df.empty:
            return {col: 0 for col in _NUMERIC_COLUMNS}
        return {col: int(df[col].sum()) for col in _NUMERIC_COLUMNS}

    def to_terminal(self) -> str:
        t = self.totals()
        lines = [
            "=" * 50,
            "FinData Pipeline - resumo da execucao",
            "=" * 50,
            f"Fonte           : {self.source}",
            f"Inicio          : {self.started_at}",
            f"Fim             : {self.finished_at}",
            f"Extraidos       : {t['extracted']}",
            f"Validos         : {t['valid']}",
            f"Rejeitados      : {t['rejected']}",
            f"Novos (insert)  : {t['inserted']}",
            f"Duplicados      : {t['duplicates']}",
            f"Revisoes        : {t['revisions']}",
            f"Erros           : {len(self.errors)}",
        ]
        for err in self.errors:
            lines.append(f"  - {err}")
        lines.append("=" * 50)
        return "\n".join(lines)

    def save(self, out_dir: str, fmt: str = "json") -> Path:
        directory = Path(out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = (
            self.started_at.replace("-", "").replace(":", "")
            .replace("T", "_").replace("Z", "")
        )

        if fmt == "csv":
            path = directory / f"report_{stamp}.csv"
            self.to_dataframe().to_csv(path, index=False)
        elif fmt == "json":
            path = directory / f"report_{stamp}.json"
            payload = {
                "source": self.source,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "totals": self.totals(),
                "by_series": [asdict(o) for o in self.outcomes],
                "errors": self.errors,
            }
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            raise ValueError(f"formato de relatorio nao suportado: {fmt}")

        logger.info("relatorio salvo em %s", path)
        return path
