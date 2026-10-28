"""Persistencia em SQLite com escrita idempotente e trilha de auditoria.

Tres tabelas mantem o pipeline rastreavel:
- ``observations``: dados validados; unicidade garantida por
  (series_id, reference_date) -> base da idempotencia.
- ``rejections``: por que cada registro foi recusado (auditoria).
- ``runs``: metadados de cada execucao, usados pelo relatorio.

As escritas acontecem dentro de transacoes e todo SQL e parametrizado.
Quando um valor muda para uma data ja existente (revisao), o historico
NAO e sobrescrito em silencio: a divergencia e contada e registrada em log.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass
class WriteStats:
    inserted: int = 0
    duplicates: int = 0
    revisions: int = 0


_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL,
    source TEXT NOT NULL,
    reference_date TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    UNIQUE (series_id, reference_date)
);

CREATE TABLE IF NOT EXISTS rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    series_id TEXT NOT NULL,
    raw_data TEXT,
    raw_value TEXT,
    reason TEXT NOT NULL,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source TEXT NOT NULL,
    extracted INTEGER DEFAULT 0,
    valid INTEGER DEFAULT 0,
    rejected INTEGER DEFAULT 0,
    inserted INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    revisions INTEGER DEFAULT 0,
    status TEXT
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row

    def initialize(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ runs
    def start_run(self, source: str, started_at: str) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO runs (started_at, source, status) VALUES (?, ?, ?)",
                (started_at, source, "running"),
            )
        return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        finished_at: str,
        *,
        extracted: int,
        valid: int,
        rejected: int,
        stats: WriteStats,
        status: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """UPDATE runs
                   SET finished_at = ?, extracted = ?, valid = ?, rejected = ?,
                       inserted = ?, duplicates = ?, revisions = ?, status = ?
                   WHERE id = ?""",
                (finished_at, extracted, valid, rejected, stats.inserted,
                 stats.duplicates, stats.revisions, status, run_id),
            )

    # ---------------------------------------------------------- observations
    def insert_observations(self, observations: Iterable[dict]) -> WriteStats:
        """Insere observacoes validas de forma idempotente, numa transacao.

        - Data inedita -> INSERT (inserted).
        - Data existente com mesmo valor -> ignorada (duplicates).
        - Data existente com valor diferente -> revisao, NAO sobrescreve
          (revisions), registrada em log.
        """
        stats = WriteStats()
        with self._conn:  # transacao unica
            for obs in observations:
                existing = self._conn.execute(
                    "SELECT value FROM observations WHERE series_id = ? AND reference_date = ?",
                    (obs["series_id"], obs["reference_date"]),
                ).fetchone()

                if existing is None:
                    self._conn.execute(
                        """INSERT INTO observations
                           (series_id, source, reference_date, value, unit, collected_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (obs["series_id"], obs["source"], obs["reference_date"],
                         obs["value"], obs["unit"], obs["collected_at"]),
                    )
                    stats.inserted += 1
                elif existing["value"] == obs["value"]:
                    stats.duplicates += 1
                else:
                    stats.revisions += 1
                    logger.warning(
                        "revisao ignorada para %s %s: armazenado=%s recebido=%s",
                        obs["series_id"], obs["reference_date"],
                        existing["value"], obs["value"],
                    )
        return stats

    def insert_rejections(
        self, run_id: Optional[int], rejections: Iterable, collected_at: str
    ) -> int:
        rows = [
            (run_id, r.series_id, r.raw_data, r.raw_value, r.reason, collected_at)
            for r in rejections
        ]
        with self._conn:
            self._conn.executemany(
                """INSERT INTO rejections
                   (run_id, series_id, raw_data, raw_value, reason, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
        return len(rows)

    # --------------------------------------------------------------- queries
    def get_observations(self, series_id: Optional[str] = None) -> list[dict]:
        if series_id:
            cur = self._conn.execute(
                "SELECT * FROM observations WHERE series_id = ? ORDER BY reference_date",
                (series_id,),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM observations ORDER BY series_id, reference_date"
            )
        return [dict(row) for row in cur.fetchall()]

    def count_observations(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        )
