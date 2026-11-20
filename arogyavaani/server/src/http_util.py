"""Shared outbound HTTP: 8 s timeout, 1 retry on network errors/5xx, structured log {tool, ms, ok}."""
import json
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger("arogya.http")
TIMEOUT_S = 8.0
_transport_override: Optional[httpx.AsyncBaseTransport] = None  # tests inject an ASGI transport for the clinic API
METRICS: list = []  # (tool, ms, ok) ring for the p50 badge


def set_transport(t: Optional[httpx.AsyncBaseTransport]) -> None:
    global _transport_override
    _transport_override = t


def log_call(tool: str, ms: float, ok: bool, **extra) -> None:
    METRICS.append((tool, ms, ok))
    del METRICS[:-500]
    logger.info(json.dumps({"tool": tool, "ms": round(ms), "ok": ok, **extra}))


async def request(tool: str, method: str, url: str, *, use_override: bool = True, **kw) -> httpx.Response:
    """Perform a request with retry. Raises the last exception if both attempts fail on network errors.
    HTTP error statuses (4xx) are returned, not raised: callers decide (e.g. 409 conflict)."""
    kw.setdefault("timeout", TIMEOUT_S)
    last_exc: Optional[Exception] = None
    for attempt in (1, 2):
        t0 = time.perf_counter()
        try:
            transport = _transport_override  # None in production; tests inject ASGI/mock transports
            async with httpx.AsyncClient(transport=transport) as c:
                r = await c.request(method, url, **kw)
            ok = r.status_code < 500
            log_call(tool, (time.perf_counter() - t0) * 1000, ok, status=r.status_code, attempt=attempt)
            if ok or attempt == 2:
                return r
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_exc = e
            log_call(tool, (time.perf_counter() - t0) * 1000, False, error=type(e).__name__, attempt=attempt)
    assert last_exc is not None
    raise last_exc
