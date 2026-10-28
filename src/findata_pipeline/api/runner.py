"""Execucao do pipeline fora do ciclo da requisicao HTTP, sem Celery/Redis.

Usa um ThreadPoolExecutor de 1 worker e um lock de processo para impedir
execucoes simultaneas. Fluxo: a rota cria a linha em `runs` (status
"running") para responder 202 com o run_id, e a tarefa em background roda
`run_pipeline` reaproveitando esse run_id.

Limitacao documentada: o lock vale para UM processo. Com multiplos workers
seria preciso um lock no banco; a linha `runs` com status="running" ja
funciona como marca persistente e e checada aqui tambem.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Callable, Optional, Sequence

from .. import config
from ..database import Database
from ..main import run_pipeline
from ..scraper import SgsClient
from ..validator import utc_now_iso

logger = logging.getLogger(__name__)


class RunConflictError(Exception):
    """Ja existe uma execucao do pipeline em andamento."""


class PipelineRunner:
    def __init__(
        self,
        db_path: str,
        client_factory: Callable[[], SgsClient] = SgsClient,
        executor=None,
    ) -> None:
        self._db_path = db_path
        self._client_factory = client_factory
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pipeline"
        )
        self._lock = threading.Lock()

    def request_run(
        self,
        series_ids: Optional[Sequence[str]] = None,
        start: Optional[date] = None,
        end: Optional[date] = None,
        trigger: str = "api",
    ) -> int:
        """Aceita uma execucao: cria a linha em runs e agenda a tarefa.

        Levanta RunConflictError se ja houver execucao em andamento.
        """
        if not self._lock.acquire(blocking=False):
            raise RunConflictError("ja existe uma execucao em andamento")
        try:
            run_id = self._create_run_row(series_ids, start, end, trigger)
        except BaseException:
            self._lock.release()
            raise
        self._executor.submit(self._execute, run_id, series_ids, start, end)
        return run_id

    def _create_run_row(self, series_ids, start, end, trigger) -> int:
        db = Database(self._db_path)
        try:
            db.initialize()
            if db.get_running_run() is not None:
                # marca persistente de execucao anterior ainda ativa
                raise RunConflictError("ja existe uma execucao em andamento")
            requested = ",".join(series_ids) if series_ids else "all"
            return db.start_run(
                config.SOURCE,
                utc_now_iso(),
                status="running",
                trigger=trigger,
                window_start=start.isoformat() if start else None,
                window_end=end.isoformat() if end else None,
                requested_series=requested,
            )
        finally:
            db.close()

    def _execute(self, run_id, series_ids, start, end) -> None:
        db = None
        try:
            db = Database(self._db_path)
            db.initialize()
            client = self._client_factory()
            run_pipeline(
                client, db, series_ids=series_ids, start=start, end=end, run_id=run_id
            )
        except Exception as exc:  # falha inesperada -> marca a run como failed
            logger.exception("execucao %s falhou", run_id)
            try:
                fdb = Database(self._db_path)
                fdb.initialize()
                fdb.set_run_failed(run_id, utc_now_iso(), str(exc))
                fdb.close()
            except Exception:
                logger.exception("nao foi possivel marcar run %s como failed", run_id)
        finally:
            if db is not None:
                db.close()
            self._lock.release()
