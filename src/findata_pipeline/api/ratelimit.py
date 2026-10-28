"""Limitador de taxa simples (janela deslizante), por processo.

Protege operacoes caras como POST /runs contra rajadas. Limitacao: vale para
UM processo; multiplos workers exigiriam um backend compartilhado.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: float) -> None:
        self.max_calls = max_calls
        self.period = period_seconds
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._calls = [t for t in self._calls if now - t < self.period]
            if len(self._calls) >= self.max_calls:
                return False
            self._calls.append(now)
            return True
