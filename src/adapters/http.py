from collections.abc import Mapping
from typing import Any

import requests

from src.adapters.base import AdapterError, AdapterPermissionError, AdapterTimeout


REDACTED_KEYS = {"token", "api_key", "apikey", "access_token", "secret", "password"}


def _redact_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    redacted = {}
    for key, value in params.items():
        redacted[key] = "<redacted>" if key.lower() in REDACTED_KEYS else value
    return redacted


class SafeHttpClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: int = 15,
        max_retries: int = 2,
        source: str = "http",
        dataset: str = "unknown",
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.source = source
        self.dataset = dataset

    def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        source: str | None = None,
        dataset: str | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        return self._request(
            "GET",
            url,
            params=params,
            source=source,
            dataset=dataset,
            **kwargs,
        )

    def post(
        self,
        url: str,
        *,
        json: Any | None = None,
        data: Any | None = None,
        source: str | None = None,
        dataset: str | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        return self._request(
            "POST",
            url,
            json=json,
            data=data,
            source=source,
            dataset=dataset,
            **kwargs,
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        source = kwargs.pop("source") or self.source
        dataset = kwargs.pop("dataset") or self.dataset
        params = kwargs.get("params")
        kwargs.setdefault("timeout", self.timeout)
        attempts = self.max_retries + 1

        last_error: AdapterError | None = None
        for attempt in range(attempts):
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.Timeout as exc:
                last_error = AdapterTimeout(source, dataset, "request timed out")
                if attempt < attempts - 1:
                    continue
                raise last_error from exc
            except requests.ConnectionError as exc:
                last_error = AdapterError(source, dataset, "connection_error")
                if attempt < attempts - 1:
                    continue
                raise last_error from exc

            status_code = getattr(response, "status_code", None)
            if status_code is None or status_code < 400:
                return response
            if status_code in {401, 403}:
                raise AdapterPermissionError(source, dataset, f"HTTP {status_code}")
            if status_code == 400:
                raise AdapterError(source, dataset, "bad_request", status_code=status_code)
            if status_code == 429 or status_code >= 500:
                last_error = AdapterError(
                    source,
                    dataset,
                    "rate_limited" if status_code == 429 else "server_error",
                    status_code=status_code,
                )
                if attempt < attempts - 1:
                    continue
                raise last_error
            raise AdapterError(source, dataset, "http_error", status_code=status_code)

        redacted = _redact_params(params)
        raise last_error or AdapterError(source, dataset, f"request_failed params={redacted}")
