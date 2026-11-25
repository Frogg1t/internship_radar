"""Shared HTTP client factory and polite retry helper for adapters."""

from __future__ import annotations

import asyncio

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
}


def build_async_client(
    timeout_seconds: float = 20.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Create a configured async HTTP client with redirects enabled."""
    return httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=True,
        transport=transport,
    )


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    retries: int = 1,
) -> httpx.Response:
    """Fetch a URL with a single transient retry on network/5xx errors."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await client.get(url)
            if response.status_code >= 500 and attempt < retries:
                await asyncio.sleep(0.75 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.75 * (attempt + 1))
    assert last_exc is not None
    raise last_exc
