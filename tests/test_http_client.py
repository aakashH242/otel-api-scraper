import base64
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper.http_client import (
    ApiKeyStrategy,
    AsyncHttpClient,
    AuthStrategy,
    AzureADStrategy,
    BasicAuthStrategy,
    OAuthStrategy,
    _maybe_await,
    build_auth_strategy,
)


@pytest.mark.asyncio
async def test_async_http_client_enforces_tls():
    client = AsyncHttpClient(max_concurrency=2, enforce_tls=True)
    with pytest.raises(httpx.HTTPError):
        await client.request("GET", "http://insecure.example.com")
    await client.close()


def test_build_auth_strategy_api_key():
    auth_cfg = cfg.ApiKeyAuthConfig(type="apikey", keyName="X-Key", keyValue="secret")
    strategy = build_auth_strategy(auth_cfg)
    assert isinstance(strategy, ApiKeyStrategy)


@pytest.mark.asyncio
async def test_api_key_strategy_headers():
    strategy = ApiKeyStrategy("X-Key", "secret")
    headers = await strategy.headers(httpx.AsyncClient())
    assert headers == {"X-Key": "secret"}


@pytest.mark.asyncio
async def test_oauth_strategy_static_token():
    cfg_obj = cfg.OAuthAuthConfig(type="oauth", token="abc123")
    strategy = OAuthStrategy(cfg_obj)
    headers = await strategy.headers(httpx.AsyncClient())
    assert headers == {"Authorization": "Bearer abc123"}


@pytest.mark.asyncio
async def test_oauth_strategy_runtime_post(monkeypatch):
    token_payload = {"access_token": "dynamic-token", "expires_in": 10}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.OAuthAuthConfig(
        type="oauth",
        username="user",
        password="pass",
        getTokenEndpoint="https://example.com/token",
        tokenKey="access_token",
        getTokenMethod="POST",
    )
    strategy = OAuthStrategy(cfg_obj)
    headers = await strategy.headers(mock_client)
    assert headers == {"Authorization": "Bearer dynamic-token"}
    mock_client.post.assert_awaited()


@pytest.mark.asyncio
async def test_oauth_strategy_runtime_get(monkeypatch):
    token_payload = {"access_token": "get-token", "expires_in": 10}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.OAuthAuthConfig(
        type="oauth",
        username="user",
        password="pass",
        getTokenEndpoint="https://example.com/token",
        tokenKey="access_token",
        getTokenMethod="GET",
        tokenHeaders={"X-Custom": "1"},
    )
    strategy = OAuthStrategy(cfg_obj)
    headers = await strategy.headers(mock_client)
    assert headers == {"Authorization": "Bearer get-token"}
    mock_client.get.assert_awaited()


@pytest.mark.asyncio
async def test_maybe_await_handles_sync_and_async_values():
    async def coro():
        return "async"

    assert await _maybe_await("plain") == "plain"
    assert await _maybe_await(coro()) == "async"


@pytest.mark.asyncio
async def test_auth_strategy_base_headers_empty():
    assert await AuthStrategy().headers(httpx.AsyncClient()) == {}


@pytest.mark.asyncio
async def test_basic_auth_strategy_encodes_credentials():
    strategy = BasicAuthStrategy("user", "pass")
    headers = await strategy.headers(httpx.AsyncClient())
    expected = base64.b64encode(b"user:pass").decode("utf-8")
    assert headers == {"Authorization": f"Basic {expected}"}


@pytest.mark.asyncio
async def test_oauth_cached_token_reused(monkeypatch):
    fake_now = datetime(2025, 1, 1)
    monkeypatch.setattr("otel_api_scraper.http_client.utc_now", lambda: fake_now)
    cfg_obj = cfg.OAuthAuthConfig(type="oauth", token="cached-token")
    strategy = OAuthStrategy(cfg_obj)
    strategy._expires_at = fake_now.timestamp() + 120
    mock_client = AsyncMock()

    token = await strategy._get_token(mock_client)

    assert token == "cached-token"
    mock_client.get.assert_not_called()
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_oauth_runtime_disabled_returns_none(monkeypatch):
    cfg_obj = cfg.OAuthAuthConfig(type="oauth", token="temp")
    strategy = OAuthStrategy(cfg_obj)
    strategy._token = None
    monkeypatch.setattr(
        "otel_api_scraper.http_client.utc_now", lambda: datetime(2025, 1, 1)
    )
    token = await strategy._get_token(AsyncMock())
    assert token is None


@pytest.mark.asyncio
async def test_oauth_refreshes_expired_token(monkeypatch):
    fake_now = datetime(2025, 1, 1)
    monkeypatch.setattr("otel_api_scraper.http_client.utc_now", lambda: fake_now)
    token_payload = {"access_token": "new-token", "expires_in": 5}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.OAuthAuthConfig(
        type="oauth",
        username="user",
        password="pass",
        getTokenEndpoint="https://example.com/token",
        tokenKey="access_token",
        getTokenMethod="POST",
    )
    strategy = OAuthStrategy(cfg_obj)
    strategy._token = "expired"
    strategy._expires_at = fake_now.timestamp() - 1

    headers = await strategy.headers(mock_client)

    assert headers == {"Authorization": "Bearer new-token"}
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_raw_body_sets_content_type(monkeypatch):
    fake_now = datetime(2025, 1, 1)
    monkeypatch.setattr("otel_api_scraper.http_client.utc_now", lambda: fake_now)
    token_payload = {"token": {"value": "raw-token"}}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.OAuthAuthConfig(
        type="oauth",
        username="user",
        password="pass",
        getTokenEndpoint="https://example.com/token",
        tokenKey="token.value",
        getTokenMethod="POST",
        bodyData=cfg.OAuthBodyData(type="raw", data="scope=a"),
        tokenHeaders={"X-Trace": "1"},
    )
    strategy = OAuthStrategy(cfg_obj)

    headers = await strategy.headers(mock_client)

    assert headers == {"Authorization": "Bearer raw-token"}
    kwargs = mock_client.post.await_args.kwargs
    assert kwargs["data"] == "scope=a"
    assert kwargs["params"] is None
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert kwargs["headers"]["X-Trace"] == "1"


@pytest.mark.asyncio
async def test_oauth_raw_body_get_sets_params(monkeypatch):
    fake_now = datetime(2025, 1, 1)
    monkeypatch.setattr("otel_api_scraper.http_client.utc_now", lambda: fake_now)
    token_payload = {"access_token": "raw-get-token"}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.OAuthAuthConfig(
        type="oauth",
        username="user",
        password="pass",
        getTokenEndpoint="https://example.com/token",
        tokenKey="access_token",
        getTokenMethod="GET",
        bodyData=cfg.OAuthBodyData(type="raw", data={"scope": "a"}),
    )
    strategy = OAuthStrategy(cfg_obj)

    headers = await strategy.headers(mock_client)

    assert headers == {"Authorization": "Bearer raw-get-token"}
    kwargs = mock_client.get.await_args.kwargs
    assert kwargs["params"] == {"scope": "a"}


@pytest.mark.asyncio
async def test_oauth_json_body_post_sets_json_payload(monkeypatch):
    fake_now = datetime(2025, 1, 1)
    monkeypatch.setattr("otel_api_scraper.http_client.utc_now", lambda: fake_now)
    token_payload = {"access_token": "json-post-token"}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.OAuthAuthConfig(
        type="oauth",
        username="user",
        password="pass",
        getTokenEndpoint="https://example.com/token",
        tokenKey="access_token",
        getTokenMethod="POST",
        bodyData=cfg.OAuthBodyData(type="json", data={"aud": "example"}),
    )
    strategy = OAuthStrategy(cfg_obj)

    headers = await strategy.headers(mock_client)

    assert headers == {"Authorization": "Bearer json-post-token"}
    kwargs = mock_client.post.await_args.kwargs
    assert kwargs["json"] == {"aud": "example"}
    assert kwargs["data"] is None


@pytest.mark.asyncio
async def test_oauth_json_body_get_sets_params(monkeypatch):
    fake_now = datetime(2025, 1, 1)
    monkeypatch.setattr("otel_api_scraper.http_client.utc_now", lambda: fake_now)
    token_payload = {"access_token": "json-token"}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.OAuthAuthConfig(
        type="oauth",
        username="user",
        password="pass",
        getTokenEndpoint="https://example.com/token",
        tokenKey="access_token",
        getTokenMethod="GET",
        bodyData=cfg.OAuthBodyData(type="json", data={"aud": "example"}),
    )
    strategy = OAuthStrategy(cfg_obj)

    headers = await strategy.headers(mock_client)

    assert headers == {"Authorization": "Bearer json-token"}
    kwargs = mock_client.get.await_args.kwargs
    assert kwargs["params"] == {"aud": "example"}
    assert kwargs["headers"] == {}


@pytest.mark.asyncio
async def test_azure_ad_fetch_and_cache(monkeypatch):
    times = iter([datetime(2025, 1, 1), datetime(2025, 1, 1, 0, 0, 10)])
    monkeypatch.setattr("otel_api_scraper.http_client.utc_now", lambda: next(times))
    token_payload = {"access_token": "azure-token", "expires_in": 120}
    mock_resp = AsyncMock()
    mock_resp.json.return_value = token_payload
    mock_resp.raise_for_status = AsyncMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    cfg_obj = cfg.AzureADAuthConfig(
        type="azuread",
        client_id="cid",
        client_secret="secret",
        tokenEndpoint="https://login.microsoftonline.com/token",
        resource="api",
    )
    strategy = AzureADStrategy(cfg_obj)

    first = await strategy.headers(mock_client)
    assert first == {"Authorization": "Bearer azure-token"}
    second = await strategy.headers(mock_client)
    assert second == {"Authorization": "Bearer azure-token"}
    mock_client.post.assert_awaited_once()


def test_build_auth_strategy_variants():
    assert build_auth_strategy(None) is None
    assert isinstance(
        build_auth_strategy(
            cfg.BasicAuthConfig(type="basic", username="u", password="p")
        ),
        BasicAuthStrategy,
    )
    assert isinstance(
        build_auth_strategy(
            cfg.ApiKeyAuthConfig(type="apikey", keyName="k", keyValue="v")
        ),
        ApiKeyStrategy,
    )
    assert isinstance(
        build_auth_strategy(cfg.OAuthAuthConfig(type="oauth", token="tkn")),
        OAuthStrategy,
    )
    assert isinstance(
        build_auth_strategy(
            cfg.AzureADAuthConfig(
                type="azuread",
                client_id="cid",
                client_secret="secret",
                tokenEndpoint="https://login.microsoftonline.com/token",
                resource="api",
            )
        ),
        AzureADStrategy,
    )
    assert build_auth_strategy("unknown") is None


@pytest.mark.asyncio
async def test_async_http_client_request_passes_through(monkeypatch):
    client = AsyncHttpClient(max_concurrency=1, enforce_tls=False)
    mock_response = object()
    client.client.request = AsyncMock(return_value=mock_response)

    result = await client.request(
        "GET", "https://example.com", headers={"X": "1"}, params={"q": "1"}
    )

    assert result is mock_response
    client.client.request.assert_awaited_once()
    await client.close()


@pytest.mark.asyncio
async def test_async_http_client_build_url():
    client = AsyncHttpClient(max_concurrency=1, enforce_tls=False)
    url = client.build_url("https://example.com/api", "/v1/resource")
    assert url == "https://example.com/api/v1/resource"
    await client.close()
