"""Cliente HTTP da API da aplicacao (nao da API publica do BCB).

Funcoes finas e testaveis: recebem uma requests.Session injetavel para que
os testes usem um transporte falso. Erros HTTP viram ApiError com o status e
o detalhe, para a UI tratar de forma compreensivel.
"""
from __future__ import annotations

from typing import Optional

import requests


class ApiError(Exception):
    def __init__(self, status_code: int, detail: Optional[str]) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class ApiClient:
    def __init__(self, base_url: str, session=None, token: Optional[str] = None, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.token = token
        self.timeout = timeout

    def _handle(self, resp):
        if resp.status_code >= 400:
            detail = None
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = getattr(resp, "text", None)
            raise ApiError(resp.status_code, detail or "erro na API")
        return resp.json()

    def _get(self, path: str, params: Optional[dict] = None):
        return self._handle(
            self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        )

    def _post(self, path: str, json: Optional[dict] = None):
        headers = {"X-API-Token": self.token} if self.token else {}
        return self._handle(
            self.session.post(
                f"{self.base_url}{path}", json=json, headers=headers, timeout=self.timeout
            )
        )

    # --- leitura ----------------------------------------------------------
    def health_ok(self) -> bool:
        try:
            return self._get("/health").get("status") == "ok"
        except Exception:
            return False

    def get_status(self) -> dict:
        return self._get("/api/v1/status")

    def get_indicators(self) -> list[dict]:
        return self._get("/api/v1/indicators")

    def get_latest(self, series_id: str) -> dict:
        return self._get(f"/api/v1/indicators/{series_id}/latest")

    def get_history(
        self,
        series_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        include_history: bool = False,
    ) -> dict:
        params: dict = {
            "limit": limit,
            "offset": offset,
            "include_history": str(include_history).lower(),
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self._get(f"/api/v1/indicators/{series_id}/history", params=params)

    def list_runs(self, limit: int = 50, offset: int = 0) -> dict:
        return self._get("/api/v1/runs", params={"limit": limit, "offset": offset})

    def get_run(self, run_id: int) -> dict:
        return self._get(f"/api/v1/runs/{run_id}")

    def get_run_status(self, run_id: int) -> dict:
        return self._get(f"/api/v1/runs/{run_id}/status")

    def list_reports(self) -> list[dict]:
        return self._get("/api/v1/reports")

    # --- escrita ----------------------------------------------------------
    def create_run(self, series_ids: Optional[list[str]] = None, days: Optional[int] = None) -> dict:
        body: dict = {}
        if series_ids:
            body["series_ids"] = series_ids
        if days:
            body["days"] = days
        return self._post("/api/v1/runs", json=body)

    # --- util -------------------------------------------------------------
    def report_download_url(self, report_id: str) -> str:
        return f"{self.base_url}/api/v1/reports/{report_id}/download"
