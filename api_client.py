"""Roostoo API client with signing, retries, and throttling."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections import deque
from typing import Any

import requests
from requests import Response

from utils import now_ms


class APIError(Exception):
    """Raised when API interaction fails after retries."""


class RoostooClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        timeout: int = 10,
        max_retries: int = 4,
        max_calls_per_minute: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_calls_per_minute = max_calls_per_minute

        self.session = requests.Session()
        self._call_timestamps: deque[float] = deque()

    def _sorted_param_string(self, params: dict[str, Any]) -> str:
        cleaned = {k: v for k, v in params.items() if v is not None}
        # Roostoo expects signing over the raw sorted key-value string.
        return "&".join(f"{k}={v}" for k, v in sorted(cleaned.items()))

    def _sign(self, param_str: str) -> str:
        signature = hmac.new(self.api_secret, param_str.encode("utf-8"), hashlib.sha256)
        return signature.hexdigest()

    def _throttle(self) -> None:
        """Global client-side rate limiting: max N calls in trailing 60s."""
        now = time.time()
        while self._call_timestamps and now - self._call_timestamps[0] > 60:
            self._call_timestamps.popleft()

        if len(self._call_timestamps) >= self.max_calls_per_minute:
            wait = 60 - (now - self._call_timestamps[0])
            if wait > 0:
                time.sleep(wait + 0.01)

        self._call_timestamps.append(time.time())

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        method = method.upper()
        params = dict(params or {})
        headers: dict[str, str] = {}

        param_str = self._sorted_param_string(params)

        if signed:
            params["timestamp"] = now_ms()
            param_str = self._sorted_param_string(params)
            headers["RST-API-KEY"] = self.api_key
            headers["MSG-SIGNATURE"] = self._sign(param_str)

        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        url = f"{self.base_url}{path}"

        for attempt in range(self.max_retries + 1):
            try:
                self._throttle()
                response: Response
                if method == "GET":
                    response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
                elif method == "POST":
                    # Use raw form-encoded body to keep signed payload and submitted body identical.
                    response = self.session.post(url, data=param_str, headers=headers, timeout=self.timeout)
                else:
                    raise APIError(f"Unsupported method: {method}")

                if response.status_code >= 500 or response.status_code == 429:
                    raise APIError(f"Transient HTTP error {response.status_code}: {response.text[:200]}")

                if response.status_code != 200:
                    raise APIError(f"HTTP {response.status_code}: {response.text[:300]}")

                try:
                    payload = response.json()
                except json.JSONDecodeError as exc:
                    raise APIError(f"Malformed JSON response: {response.text[:300]}") from exc

                if not isinstance(payload, dict):
                    raise APIError("Unexpected response payload type (expected JSON object)")

                return payload

            except (requests.RequestException, APIError) as exc:
                is_last = attempt >= self.max_retries
                if is_last:
                    raise APIError(f"{method} {path} failed after retries: {exc}") from exc
                backoff = min(2**attempt, 16)
                time.sleep(backoff)

        raise APIError(f"Unreachable request failure path for {method} {path}")

    def get_server_time(self) -> dict[str, Any]:
        return self._request("GET", "/v3/serverTime")

    def get_exchange_info(self) -> dict[str, Any]:
        return self._request("GET", "/v3/exchangeInfo")

    def get_ticker(self, pair: str | None = None) -> dict[str, Any]:
        params = {"pair": pair} if pair else {}
        try:
            return self._request("GET", "/v3/ticker", params=params)
        except APIError as exc:
            if "Missed Key: timestamp" in str(exc):
                return self._request("GET", "/v3/ticker", params=params, signed=True)
            raise

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/v3/balance", signed=True)

    def get_pending_count(self) -> dict[str, Any]:
        return self._request("GET", "/v3/pending_count", signed=True)

    def place_order(self, pair: str, side: str, order_type: str, quantity: float) -> dict[str, Any]:
        params = {
            "pair": pair,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }
        return self._request("POST", "/v3/place_order", params=params, signed=True)

    def query_order(
        self,
        order_id: str | None = None,
        pair: str | None = None,
        pending_only: bool | None = None,
    ) -> dict[str, Any]:
        # This Roostoo environment allows only one of order_id or pair.
        query_pair = None if order_id else pair
        params = {"order_id": order_id, "pair": query_pair}
        if order_id is None and query_pair is None and pending_only is not None:
            params["pending_only"] = int(bool(pending_only))
        return self._request("POST", "/v3/query_order", params=params, signed=True)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("POST", "/v3/cancel_order", params={"order_id": order_id}, signed=True)
