"""HTTP client wrappers and auth strategies."""

from __future__ import annotations

import asyncio
import base64
import inspect
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from . import config as cfg
from .utils import lookup_path, utc_now


async def _maybe_await(value: Any) -> Any:
    """Await the value if it is awaitable (supports async-friendly mocks)."""
    if inspect.isawaitable(value):
        return await value
    return value


class AuthStrategy:
    """Base interface for authentication header injection."""

    async def headers(self, client: httpx.AsyncClient) -> Dict[str, str]:
        """Return headers to include for authenticated requests."""
        return {}


class BasicAuthStrategy(AuthStrategy):
    """HTTP basic authentication strategy."""

    def __init__(self, username: str, password: str):
        """Create a basic auth strategy.

        Args:
            username: Basic auth username.
            password: Basic auth password.
        """
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode(
            "utf-8"
        )
        self._header = {"Authorization": f"Basic {token}"}

    async def headers(self, client: httpx.AsyncClient) -> Dict[str, str]:
        """Return static basic auth header."""
        return self._header


class ApiKeyStrategy(AuthStrategy):
    """Header-based API key authentication strategy."""

    def __init__(self, key_name: str, key_value: str):
        """Create an API key strategy.

        Args:
            key_name: Header name to hold the key.
            key_value: API key value.
        """
        self.key_name = key_name
        self.key_value = key_value

    async def headers(self, client: httpx.AsyncClient) -> Dict[str, str]:
        """Return header carrying the API key."""
        return {self.key_name: self.key_value}


class OAuthStrategy(AuthStrategy):
    """OAuth bearer token strategy supporting static or runtime tokens."""

    def __init__(self, cfg_obj: cfg.OAuthAuthConfig):
        """Create OAuth strategy.

        Args:
            cfg_obj: OAuth configuration.
        """
        self.cfg = cfg_obj
        self._token: Optional[str] = cfg_obj.token
        self._expires_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def headers(self, client: httpx.AsyncClient) -> Dict[str, str]:
        """Return bearer token header."""
        token = await self._get_token(client)
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def _get_token(self, client: httpx.AsyncClient) -> Optional[str]:
        """Fetch or reuse an OAuth token with basic refresh logic."""
        async with self._lock:
            now = utc_now().timestamp()
            if self._token and (
                self._expires_at is None or now < self._expires_at - 30
            ):
                return self._token
            if not self.cfg.runtime:
                return self._token
            headers: Dict[str, str] = dict(self.cfg.tokenHeaders or {})
            params: Dict[str, Any] | None = None
            data: Any = None
            json_body: Any = None
            if self.cfg.bodyData:
                if self.cfg.bodyData.type == "json":
                    if self.cfg.getTokenMethod == "GET":
                        params = (
                            self.cfg.bodyData.data
                            if isinstance(self.cfg.bodyData.data, dict)
                            else None
                        )
                    else:
                        json_body = self.cfg.bodyData.data
                else:
                    # raw
                    if self.cfg.getTokenMethod == "GET":
                        params = (
                            self.cfg.bodyData.data
                            if isinstance(self.cfg.bodyData.data, dict)
                            else None
                        )
                    else:
                        data = self.cfg.bodyData.data
                        headers.setdefault(
                            "Content-Type", "application/x-www-form-urlencoded"
                        )

            request_kwargs = {
                "headers": headers,
                "auth": (self.cfg.username, self.cfg.password)
                if self.cfg.username and self.cfg.password
                else None,
                "timeout": 20.0,
            }
            if self.cfg.getTokenMethod == "GET":
                response = await client.get(
                    self.cfg.getTokenEndpoint,
                    params=params,
                    **request_kwargs,
                )
            else:
                response = await client.post(
                    self.cfg.getTokenEndpoint,
                    params=params,
                    data=data,
                    json=json_body,
                    **request_kwargs,
                )
            await _maybe_await(response.raise_for_status())
            payload = await _maybe_await(response.json())
            token = (
                lookup_path(payload, self.cfg.tokenKey) if self.cfg.tokenKey else None
            )
            self._token = token or payload.get("access_token")
            if "expires_in" in payload:
                self._expires_at = now + float(payload["expires_in"])
            return self._token


class AzureADStrategy(AuthStrategy):
    """Azure AD client credential strategy."""

    def __init__(self, cfg_obj: cfg.AzureADAuthConfig):
        """Create Azure AD strategy.

        Args:
            cfg_obj: Azure AD configuration.
        """
        self.cfg = cfg_obj
        self._token: Optional[str] = None
        self._expires_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def headers(self, client: httpx.AsyncClient) -> Dict[str, str]:
        """Return Azure AD bearer token header."""
        token = await self._get_token(client)
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def _get_token(self, client: httpx.AsyncClient) -> Optional[str]:
        """Fetch or reuse an Azure AD token with expiry tracking."""
        async with self._lock:
            now = utc_now().timestamp()
            if self._token and self._expires_at and now < self._expires_at - 30:
                return self._token
            data = {
                "grant_type": "client_credentials",
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
                "resource": self.cfg.resource,
            }
            response = await client.post(
                self.cfg.tokenEndpoint, data=data, timeout=20.0
            )
            await _maybe_await(response.raise_for_status())
            payload = await _maybe_await(response.json())
            self._token = payload.get("access_token")
            if "expires_in" in payload:
                self._expires_at = now + float(payload["expires_in"])
            return self._token


def build_auth_strategy(auth: Optional[cfg.AuthConfig]) -> Optional[AuthStrategy]:
    """Instantiate an auth strategy from config."""
    if auth is None:
        return None
    if isinstance(auth, cfg.BasicAuthConfig):
        return BasicAuthStrategy(auth.username, auth.password)
    if isinstance(auth, cfg.ApiKeyAuthConfig):
        return ApiKeyStrategy(auth.keyName, auth.keyValue)
    if isinstance(auth, cfg.OAuthAuthConfig):
        return OAuthStrategy(auth)
    if isinstance(auth, cfg.AzureADAuthConfig):
        return AzureADStrategy(auth)
    return None


class AsyncHttpClient:
    """Thin wrapper to enforce global concurrency and TLS policy."""

    def __init__(self, max_concurrency: int, enforce_tls: bool):
        """Initialize the HTTP client.

        Args:
            max_concurrency: Global max concurrent requests.
            enforce_tls: Whether to require HTTPS.
        """
        self._sem = asyncio.Semaphore(max_concurrency)
        self.enforce_tls = enforce_tls
        self.client = httpx.AsyncClient(http2=True, verify=enforce_tls)
        self._logger = None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Any = None,
        json: Any = None,
    ) -> httpx.Response:
        """Perform an HTTP request respecting global concurrency and TLS policy."""
        if self.enforce_tls and url.lower().startswith("http://"):
            raise httpx.HTTPError("TLS enforced but non-HTTPS URL requested")
        async with self._sem:
            if self._logger is None:
                import logging

                self._logger = logging.getLogger(__name__)
            self._logger.debug(
                "HTTP %s %s headers=%s params=%s", method, url, headers, params
            )
            response = await self.client.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                json=json,
                timeout=60.0,
            )
            return response

    def build_url(self, base_url: str, endpoint: str) -> str:
        """Join base URL and endpoint into a full URL."""
        return urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))
