"""Dependencias do FastAPI: conexao por requisicao, runner e autenticacao.

Nao compartilha a conexao unica de Database entre threads: cada requisicao
abre e fecha o seu Database (o WAL permite leitura concorrente).
"""
from __future__ import annotations

import secrets
from typing import Iterator, Optional

from fastapi import Header, HTTPException, Request, status

from ..database import Database
from .runner import PipelineRunner


def get_db(request: Request) -> Iterator[Database]:
    db = Database(request.app.state.db_path)
    try:
        yield db
    finally:
        db.close()


def get_runner(request: Request) -> PipelineRunner:
    return request.app.state.runner


def require_write_auth(
    request: Request, x_api_token: Optional[str] = Header(default=None)
) -> None:
    """Protege operacoes de escrita. Se nenhum token esta configurado, libera
    (aceitavel apenas em ambiente estritamente local). Comparacao segura."""
    token = getattr(request.app.state, "write_token", "") or ""
    if not token:
        return
    if not x_api_token or not secrets.compare_digest(x_api_token, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token de escrita invalido ou ausente",
        )


def rate_limit_runs(request: Request) -> None:
    """Limita a frequencia de POST /runs (429 quando excede)."""
    limiter = getattr(request.app.state, "run_limiter", None)
    if limiter is not None and not limiter.allow():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="muitas solicitacoes de execucao; tente novamente em instantes",
            headers={"Retry-After": "30"},
        )
