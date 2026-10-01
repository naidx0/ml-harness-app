from __future__ import annotations

import json
import urllib.request
from typing import Any

from app import security
from app.config import BASE_URL


class HarnessRun:
    """Small standard-library client for an ML Harness run."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.run_id: int | None = None

    def _headers(self) -> dict[str, str]:
        """Content type plus the engine token, read from `engine.json`.

        Read per request rather than cached at construction, so a client built
        before the engine started still authenticates once it has. If no token
        can be found the request goes out without one and comes back 401, which
        is a better error than a locally invented token that never matches.
        """
        headers = {"Content-Type": "application/json"}
        headers.update(security.auth_header())
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    def create(self, name: str, params: dict[str, Any] | None = None) -> "HarnessRun":
        result = self._post("/api/runs", {"name": name, "params": params or {}})
        self.run_id = int(result["id"])
        return self

    def log(self, step: int, name: str, value: float) -> dict[str, Any]:
        if self.run_id is None:
            raise RuntimeError("create() must be called before log()")
        return self._post(
            f"/api/runs/{self.run_id}/metrics",
            {"step": step, "name": name, "value": value},
        )

    def complete(self) -> dict[str, Any]:
        if self.run_id is None:
            raise RuntimeError("create() must be called before complete()")
        return self._post(f"/api/runs/{self.run_id}/complete", {})
