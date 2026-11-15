"""Polite HTTP for external metadata sources (OpenAlex, Semantic Scholar, NTRS, DataCite).

- Minimum interval between calls per source; honours ``Retry-After`` on 429/503
  with exponential back-off; gives up with an explicit error.
- Successful JSON responses are cached on disk (key = method + URL + params + body),
  so re-runs are incremental and every answer used is auditable.
- Generic User-Agent; no personal data is ever sent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)
USER_AGENT = "flame-in-freefall-research/0.1 (open research prototype)"


class SourceError(RuntimeError):
    pass


@dataclass
class SourceLimits:
    min_interval_s: float = 1.0
    max_retries: int = 5
    timeout_s: float = 60.0


class PoliteClient:
    def __init__(self, source: str, cache_dir: Path, limits: SourceLimits, session: requests.Session | None = None):
        self.source = source
        self.limits = limits
        self.cache_dir = cache_dir / source
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self._last = 0.0
        self.network_calls = 0
        self.cache_hits = 0

    def _key(self, method: str, url: str, params: dict | None, body: Any) -> Path:
        raw = json.dumps([method, url, params or {}, body], sort_keys=True, ensure_ascii=False)
        return self.cache_dir / (hashlib.sha256(raw.encode()).hexdigest()[:32] + ".json")

    def request_json(
        self, method: str, url: str, *, params: dict | None = None, body: Any = None, allow_404: bool = False
    ) -> Any:
        key = self._key(method, url, params, body)
        if key.exists():
            self.cache_hits += 1
            return json.loads(key.read_text(encoding="utf-8"))["response"]
        delay = self.limits.min_interval_s
        for attempt in range(self.limits.max_retries + 1):
            wait = self.limits.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.request(method, url, params=params, json=body, timeout=self.limits.timeout_s)
            except requests.RequestException as exc:
                resp, err = None, exc
            finally:
                self._last = time.monotonic()
                self.network_calls += 1
            if resp is not None and resp.status_code == 200:
                data = resp.json()
                key.write_text(
                    json.dumps(
                        {
                            "source": self.source,
                            "method": method,
                            "url": url,
                            "params": params,
                            "body": body,
                            "fetched_at": datetime.now(UTC).isoformat(),
                            "response": data,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return data
            if resp is not None and resp.status_code == 404 and allow_404:
                return None
            retryable = resp is None or resp.status_code in (429, 500, 502, 503, 504)
            if not retryable or attempt == self.limits.max_retries:
                status = "network error" if resp is None else f"HTTP {resp.status_code}"
                raise SourceError(f"{self.source}: {method} {url} failed ({status})") from (
                    err if resp is None else None
                )
            retry_after = resp.headers.get("Retry-After") if resp is not None else None
            sleep = float(retry_after) if retry_after and retry_after.isdigit() else delay
            log.warning("%s: %s, retrying in %.1fs", self.source, "throttled" if resp is not None else "error", sleep)
            time.sleep(sleep)
            delay = min(delay * 2, 60)
        raise SourceError(f"{self.source}: exhausted retries")  # pragma: no cover
