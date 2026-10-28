"""Fabrica da aplicacao FastAPI.

Monta CORS, routers e handlers de erro, e garante o schema do banco na
subida (idempotente, sem apagar dados). A orquestracao de negocio fica na
camada de servicos; aqui so se traduz HTTP.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import config
from ..database import Database
from .ratelimit import RateLimiter
from .routes import health, indicators, reports, runs
from .routes import status as status_routes
from .runner import PipelineRunner, RunConflictError
from .services import InvalidReportIdError, ReportNotFoundError, UnknownSeriesError

logger = logging.getLogger(__name__)

DESCRIPTION = """
API REST do **FinData Pipeline**: expoe indicadores financeiros publicos do
Banco Central (CDI, Selic, IPCA) coletados, validados e versionados pelo
pipeline.

**Precisao decimal:** o campo `value` e sempre uma **string** (texto
canonico do Decimal, ex. `"0.040168"`), nunca um float — para preservar a
precisao exigida em dados financeiros.
""".strip()


def create_app(
    *,
    db_path: Optional[str] = None,
    runner: Optional[PipelineRunner] = None,
    write_token: Optional[str] = None,
    cors_origins: Optional[list[str]] = None,
) -> FastAPI:
    db_path = db_path or config.DB_PATH

    app = FastAPI(title="FinData Pipeline API", version="2.0.0", description=DESCRIPTION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else config.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.db_path = db_path
    app.state.runner = runner or PipelineRunner(db_path)
    app.state.write_token = config.API_WRITE_TOKEN if write_token is None else write_token
    app.state.run_limiter = RateLimiter(config.RUN_RATE_LIMIT_MAX, config.RUN_RATE_LIMIT_WINDOW_S)

    # Garante o schema (cria tabelas/colunas que faltam) sem apagar dados.
    _db = Database(db_path)
    _db.initialize()
    _db.close()

    app.include_router(health.router)
    app.include_router(status_routes.router)
    app.include_router(indicators.router)
    app.include_router(runs.router)
    app.include_router(reports.router)

    @app.exception_handler(UnknownSeriesError)
    async def _unknown_series(_request, exc):  # noqa: ANN001
        return JSONResponse(status_code=404, content={"detail": f"serie desconhecida: {exc}"})

    @app.exception_handler(RunConflictError)
    async def _run_conflict(_request, exc):  # noqa: ANN001
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidReportIdError)
    async def _invalid_report(_request, _exc):  # noqa: ANN001
        return JSONResponse(status_code=400, content={"detail": "identificador de relatorio invalido"})

    @app.exception_handler(ReportNotFoundError)
    async def _report_not_found(_request, _exc):  # noqa: ANN001
        return JSONResponse(status_code=404, content={"detail": "relatorio inexistente"})

    return app


app = create_app()
