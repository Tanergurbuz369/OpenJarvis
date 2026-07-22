"""Client for the public n8n template API (``api.n8n.io``).

This is the same API that powers the n8n.io template gallery and third-party
viewers over it. It is public and read-only; no authentication is required.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.n8n.io/api/templates"


class N8nTemplateClient:
    """Paginated, retrying client over the n8n template API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff: float = 1.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self._client: Any = None

    # -- lifecycle -----------------------------------------------------
    def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                trust_env=True,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "N8nTemplateClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- low-level -----------------------------------------------------
    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        import httpx

        url = f"{self.base_url}/{path.lstrip('/')}"
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._http().get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:  # network or JSON error
                last_exc = exc
                if attempt < self.max_retries:
                    wait = self.backoff**attempt
                    logger.debug(
                        "n8n API %s failed (attempt %d/%d): %s; retrying in %.1fs",
                        url,
                        attempt,
                        self.max_retries,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
        raise RuntimeError(f"n8n API request failed: {url}: {last_exc}")

    # -- public --------------------------------------------------------
    def total_workflows(self) -> int:
        """Return the total number of workflows available upstream."""
        data = self._get("search", {"page": 1, "rows": 1})
        return int(data.get("totalWorkflows") or 0)

    def categories(self) -> List[Dict[str, Any]]:
        """Return the list of template categories."""
        data = self._get("categories")
        return list(data.get("categories") or [])

    def list_workflows(
        self,
        *,
        page: int = 1,
        rows: int = 100,
        search: Optional[str] = None,
        category: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return one page of the workflow listing (raw API response).

        Uses the ``/search`` endpoint, whose ``page`` parameter genuinely
        paginates (the ``/workflows`` endpoint ignores ``page``).
        """
        params: Dict[str, Any] = {"page": page, "rows": rows}
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        return self._get("search", params)

    def iter_workflows(
        self,
        *,
        rows: int = 100,
        search: Optional[str] = None,
        category: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield workflow list objects across all pages.

        Stops when a page repeats/returns nothing, ``seen`` reaches the reported
        total, or ``max_pages`` is reached. Yielded ids are de-duplicated so a
        server-side quirk cannot produce an infinite loop.
        """
        page = 1
        total: Optional[int] = None
        seen_ids: set = set()
        while True:
            data = self.list_workflows(
                page=page, rows=rows, search=search, category=category
            )
            if total is None:
                total = int(data.get("totalWorkflows") or 0)
            workflows = data.get("workflows") or []
            fresh = [w for w in workflows if w.get("id") not in seen_ids]
            if not fresh:
                return
            for wf in fresh:
                seen_ids.add(wf.get("id"))
                yield wf
            if total and len(seen_ids) >= total:
                return
            if max_pages is not None and page >= max_pages:
                return
            page += 1

    def get_workflow(self, workflow_id: int) -> Dict[str, Any]:
        """Return the full detail object for a single workflow.

        The returned dict is the API's ``workflow`` payload, which contains
        metadata plus a nested ``workflow`` graph (nodes/connections) suitable
        for import into n8n.
        """
        data = self._get(f"workflows/{int(workflow_id)}")
        return data.get("workflow") or data
