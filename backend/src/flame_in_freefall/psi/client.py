"""Thin HTTP client for the PSI geode-py web service.

``get_download_url`` returns a short-lived signed URL. Callers must never log or
persist it; fetching bytes is done by ``psi.download`` with size limits.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .schemas import (
    FilesResponse,
    InvestigationDetail,
    PsiSchemaError,
    SearchResponse,
    parse,
)

log = logging.getLogger(__name__)

BASE_URL = "https://psi.nasa.gov/geode-py/ws"
USER_AGENT = "flame-in-freefall-inventory/0.1 (+research prototype)"


class PsiClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        session: requests.Session | None = None,
        pause_s: float = 0.5,
        connect_timeout_s: float = 10.0,
        read_timeout_s: float = 300.0,
        retries: int = 5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.pause_s = pause_s
        self.timeout = (connect_timeout_s, read_timeout_s)
        self.calls = 0
        self._last_call = 0.0
        if session is None:
            session = requests.Session()
            retry = Retry(
                total=retries,
                backoff_factor=1.0,
                status_forcelist=(429, 500, 502, 503, 504),
                # POST /files/v2 is a read-only query, safe to retry.
                allowed_methods=frozenset({"GET", "POST"}),
                respect_retry_after_header=True,
            )
            session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.setdefault("User-Agent", USER_AGENT)
        self.session = session

    # -- transport --------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._send(method, path, **kwargs)
        ctype = resp.headers.get("Content-Type", "")
        if "json" not in ctype:
            raise PsiSchemaError(f"{method} {path}: expected JSON, got {ctype!r}")
        return resp.json()

    def _send(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        wait = self.pause_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        finally:
            self._last_call = time.monotonic()
            self.calls += 1
        log.debug("%s %s -> %s", method, path, resp.status_code)
        if resp.status_code != 200:
            raise requests.HTTPError(f"{method} {path} returned HTTP {resp.status_code}", response=resp)
        return resp

    # -- endpoints --------------------------------------------------------

    def filter_options(self) -> dict[str, Any]:
        return self._request("GET", "/repo/filter-options")

    def search_page(
        self,
        *,
        offset: int,
        size: int,
        field: str | None = None,
        value: str | None = None,
    ) -> tuple[SearchResponse, dict[str, Any]]:
        params: dict[str, Any] = {"source": "psi", "type": "investigation", "from": offset, "size": size}
        if field is not None:
            params["ffield"], params["fvalue"] = field, value
        raw = self._request("GET", "/repo/search", params=params)
        return parse(SearchResponse, raw, f"search from={offset}"), raw

    def search_investigations(
        self, *, field: str | None = None, value: str | None = None, page_size: int = 50
    ) -> list[dict[str, Any]]:
        """Return every ``_source`` matching the filter, paging until ``hits.total``."""
        sources: list[dict[str, Any]] = []
        total: int | None = None
        offset = 0
        while total is None or offset < total:
            parsed, raw = self.search_page(offset=offset, size=page_size, field=field, value=value)
            if total is None:
                total = parsed.hits.total
            elif parsed.hits.total != total:
                raise PsiSchemaError(f"search total changed while paging ({total} -> {parsed.hits.total})")
            page = [h["_source"] for h in raw["hits"]["hits"]]
            if not page:
                break
            sources.extend(page)
            offset += len(page)
        if total is not None and len(sources) != total:
            raise PsiSchemaError(f"search returned {len(sources)} records but reported total={total}")
        return sources

    def get_investigation(self, accession: str) -> tuple[InvestigationDetail, dict[str, Any]]:
        raw = self._request("GET", f"/repo/investigations/{accession}")
        detail = parse(InvestigationDetail, raw, f"investigation {accession}")
        if detail.accession != accession:
            raise PsiSchemaError(f"asked for {accession}, got {detail.accession}")
        return detail, raw

    def get_file_tree(self, accession: str, version: int) -> FilesResponse:
        body = {
            "folder": "",
            "fileType": "study",
            "studyId": accession,
            "version": version,
            "obfuscationcode": "",
        }
        raw = self._request("POST", "/files/v2", json=body)
        return parse(FilesResponse, raw, f"files/v2 {accession} v{version}")

    def get_download_url(self, accession: str, file_name: str, file_version: int) -> str:
        """Signed URL for one file. ``file`` is the bare file name (observed: a
        full path returns 404); ``version`` is the file record's version."""
        resp = self._send(
            "GET",
            f"/studies/{accession}/download",
            params={"file": file_name, "version": file_version, "redirect": "false"},
        )
        url = resp.text.strip().strip('"')
        if not url.startswith("https://") or len(url.split()) != 1:
            raise PsiSchemaError(f"download {accession}/{file_name}: response is not a single https URL")
        return url
