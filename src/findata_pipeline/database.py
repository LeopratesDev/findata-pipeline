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
    version INTEGER NOT NULL DEFAULT 1,
    is_current INTEGER NOT NULL DEFAULT 1,
    superseded_at TEXT
);

-- No maximo uma versao "atual" por (serie, data); as versoes anteriores
-- ficam no historico com is_current = 0. Indice parcial (recurso do SQLite)
-- garante a integridade da regra no nivel do banco.
CREATE UNIQUE INDEX IF NOT EXISTS ux_observations_current
    ON observations (series_id, reference_date) WHERE is_current = 1;

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
        # timeout: espera ate 30s por um bloqueio antes de falhar, em vez de
        # erro imediato quando a futura API e o pipeline tocam o mesmo arquivo.
        self._conn = sqlite3.connect(path, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        # WAL permite leituras concorrentes enquanto ha uma escrita em curso;
        # sem ele qualquer escrita bloqueia os leitores. A configuracao fica
        # gravada no arquivo (basta setar uma vez) e e segura para o uso via
        # CLI; em :memory: o PRAGMA e um no-op inofensivo.
        self._conn.execute("PRAGMA journal_mode = WAL")

    # Colunas acrescentadas na v2 (API). Migracao aditiva: nunca recria a
    # tabela runs nem apaga dados existentes.
    _RUNS_EXTRA_COLUMNS = {
        "window_start": "TEXT",
        "window_end": "TEXT",
        "requested_series": "TEXT",
        "error_detail": "TEXT",
        "trigger": "TEXT",
    }

    def initialize(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)
        self._migrate_runs()

    def _migrate_runs(self) -> None:
        """Migracao aditiva e idempotente: adiciona a runs as colunas que
        faltam (PRAGMA table_info + ALTER TABLE ADD COLUMN), preservando os
        dados. Os nomes vem de uma lista fixa interna, nunca de entrada externa."""
        existing = {row["name"] for row in self._conn.execute("PRAGMA table_info(runs)")}
        with self._conn:
            for column, coltype in self._RUNS_EXTRA_COLUMNS.items():
                if column not in existing:
                    self._conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {coltype}")
                    logger.info("migracao: coluna runs.%s adicionada", column)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ runs
    def start_run(
        self,
        source: str,
        started_at: str,
        *,
        status: str = "running",
        trigger: str = "cli",
        window_start: Optional[str] = None,
        window_end: Optional[str] = None,
        requested_series: Optional[str] = None,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                """INSERT INTO runs
                   (started_at, source, status, trigger,
                    window_start, window_end, requested_series)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (started_at, source, status, trigger,
                 window_start, window_end, requested_series),
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
        error_detail: Optional[str] = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """UPDATE runs
                   SET finished_at = ?, extracted = ?, valid = ?, rejected = ?,
                       inserted = ?, duplicates = ?, revisions = ?, status = ?,
                       error_detail = ?
                   WHERE id = ?""",
                (finished_at, extracted, valid, rejected, stats.inserted,
                 stats.duplicates, stats.revisions, status, error_detail, run_id),
            )

    def set_run_failed(self, run_id: int, finished_at: str, error_detail: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET finished_at = ?, status = 'failed', error_detail = ? WHERE id = ?",
                (finished_at, error_detail, run_id),
            )

    def get_runs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in cur.fetchall()]

    def count_runs(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def get_run(self, run_id: int) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_running_run(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE status = 'running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_last_successful_run(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE status IN ('done', 'completed_with_errors') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_rejections(self, run_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM rejections WHERE run_id = ? ORDER BY id", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]

    # ---------------------------------------------------------- observations
    def insert_observations(self, observations: Iterable[dict]) -> WriteStats:
        """Insere observacoes validas de forma idempotente e versionada.

        - Data inedita -> INSERT como versao 1, atual (inserted).
        - Data existente com mesmo valor atual -> ignorada (duplicates).
        - Data existente com valor diferente -> revisao: a versao atual e
          aposentada (is_current = 0, superseded_at preenchido) e a nova
          entra como versao incrementada e atual (revisions). O historico
          e preservado - nada e apagado.
        """
        stats = WriteStats()
        with self._conn:  # transacao unica
            for obs in observations:
                current = self._conn.execute(
                    """SELECT id, value, version FROM observations
                       WHERE series_id = ? AND reference_date = ? AND is_current = 1""",
                    (obs["series_id"], obs["reference_date"]),
                ).fetchone()

                if current is None:
                    self._insert_version(obs, version=1)
                    stats.inserted += 1
                elif current["value"] == obs["value"]:
                    stats.duplicates += 1
                else:
                    self._conn.execute(
                        "UPDATE observations SET is_current = 0, superseded_at = ? WHERE id = ?",
                        (obs["collected_at"], current["id"]),
                    )
                    self._insert_version(obs, version=current["version"] + 1)
                    stats.revisions += 1
                    logger.info(
                        "revisao registrada para %s %s: %s -> %s (v%d)",
                        obs["series_id"], obs["reference_date"],
                        current["value"], obs["value"], current["version"] + 1,
                    )
        return stats

    def _insert_version(self, obs: dict, version: int) -> None:
        self._conn.execute(
            """INSERT INTO observations
               (series_id, source, reference_date, value, unit, collected_at,
                version, is_current, superseded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, NULL)""",
            (obs["series_id"], obs["source"], obs["reference_date"],
             obs["value"], obs["unit"], obs["collected_at"], version),
        )

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
    def get_observations(
        self, series_id: Optional[str] = None, include_history: bool = False
    ) -> list[dict]:
        """Retorna observacoes. Por padrao, apenas as versoes atuais;
        include_history=True traz tambem as versoes aposentadas."""
        clauses: list[str] = []
        params: list = []
        if not include_history:
            clauses.append("is_current = 1")
        if series_id:
            clauses.append("series_id = ?")
            params.append(series_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        cur = self._conn.execute(
            f"SELECT * FROM observations{where} ORDER BY series_id, reference_date, version",
            params,
        )
        return [dict(row) for row in cur.fetchall()]

    def get_history(self, series_id: str, reference_date: str) -> list[dict]:
        """Todas as versoes (antigas e atual) de uma (serie, data)."""
        cur = self._conn.execute(
            """SELECT * FROM observations
               WHERE series_id = ? AND reference_date = ? ORDER BY version""",
            (series_id, reference_date),
        )
        return [dict(row) for row in cur.fetchall()]

    def count_observations(self) -> int:
        """Numero de observacoes atuais (exclui versoes aposentadas)."""
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM observations WHERE is_current = 1"
            ).fetchone()[0]
        )

    def get_latest(self, series_id: str) -> Optional[dict]:
        """Ultima observacao vigente de uma serie (maior reference_date)."""
        row = self._conn.execute(
            """SELECT * FROM observations
               WHERE series_id = ? AND is_current = 1
               ORDER BY reference_date DESC LIMIT 1""",
            (series_id,),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _obs_filter(series_id, start, end, include_history):
        clauses: list[str] = []
        params: list = []
        if not include_history:
            clauses.append("is_current = 1")
        if series_id:
            clauses.append("series_id = ?")
            params.append(series_id)
        if start:
            clauses.append("reference_date >= ?")
            params.append(start)
        if end:
            clauses.append("reference_date <= ?")
            params.append(end)
        return clauses, params

    def query_observations(
        self,
        series_id: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        include_history: bool = False,
    ) -> list[dict]:
        """Historico filtrado/paginado (reference_date em ISO permite
        comparacao por string). Ordena do mais recente para o mais antigo."""
        clauses, params = self._obs_filter(series_id, start, end, include_history)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM observations{where} ORDER BY reference_date DESC, version DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = params + [limit, offset]
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def count_observations_query(
        self,
        series_id: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        include_history: bool = False,
    ) -> int:
        clauses, params = self._obs_filter(series_id, start, end, include_history)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return int(
            self._conn.execute(f"SELECT COUNT(*) FROM observations{where}", params).fetchone()[0]
        )
