"""Perf guards for GET /deals and GET /discovery/home (round trips, overlap, caching)."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.routers import catalog as catalog_mod
from app.routers import discovery as discovery_mod
from app.routers import retention as retention_mod
from app.routers.catalog import catalog_item_from_candidate
from app.routers.retention import DealOut
from app.services.discovery import home as home_mod
from starlette.responses import Response
from tests.test_discovery_home_rate_counter import _empty_home_payload
from tests.test_retention_and_recommendations import POOL


class _MemCache:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.sets = 0

    def get(self, key: str, **_: Any) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: Any, **_: Any) -> None:
        self.sets += 1
        self.data[key] = value


def _deal(deal_id: str, ends_at: datetime) -> DealOut:
    return DealOut(
        deal_id=deal_id,
        starts_at=(ends_at - timedelta(hours=2)).isoformat(),
        ends_at=ends_at.isoformat(),
        deal_price_ngwee=5_000,
        reference_price_ngwee=8_000,
        discount_percent=37,
        listing=catalog_item_from_candidate(POOL[1]),
    )


def test_deals_second_request_served_from_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _MemCache()
    monkeypatch.setattr(retention_mod, "get_cached_json", cache.get)
    monkeypatch.setattr(retention_mod, "set_cached_json", cache.set)
    now = datetime.now(UTC)
    calls = {"n": 0}

    def _live(*_a: Any, **_k: Any) -> list[DealOut]:
        calls["n"] += 1
        return [
            _deal("live", now + timedelta(hours=1)),
            _deal("soon-expired", now + timedelta(seconds=5)),
        ]

    monkeypatch.setattr(retention_mod, "live_deals", _live)
    first = retention_mod._cached_live_deals(MagicMock(), now=now, limit=24)
    second = retention_mod._cached_live_deals(MagicMock(), now=now, limit=24)
    assert calls["n"] == 1 and cache.sets == 1  # one build, DB touched once
    assert [d.deal_id for d in first] == [d.deal_id for d in second]
    # Deals that expired inside the TTL are dropped at read time.
    later = retention_mod._cached_live_deals(MagicMock(), now=now + timedelta(seconds=30), limit=24)
    assert [d.deal_id for d in later] == ["live"]
    assert calls["n"] == 1


def test_deals_limiter_overlaps_with_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def _slow_limit(*_a: Any, **_k: Any) -> None:
        time.sleep(0.15)

    def _slow_read(*_a: Any, **_k: Any) -> list[DealOut]:
        time.sleep(0.15)
        return []

    monkeypatch.setattr(retention_mod, "_limit_public_read", _slow_limit)
    monkeypatch.setattr(retention_mod, "_cached_live_deals", _slow_read)
    monkeypatch.setattr(retention_mod, "get_client_ip", lambda _r: "1.2.3.4")
    response = Response()
    t0 = time.perf_counter()
    out = retention_mod.list_deals(MagicMock(), response, MagicMock(), limit=24)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.27, f"limiter and read should overlap, took {elapsed:.3f}s"
    assert out.items == []
    assert "s-maxage" in response.headers["cache-control"]


def test_deals_rate_limit_still_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    def _deny(*_a: Any, **_k: Any) -> None:
        raise AppError(code="rate_limited", message="x", http_status=429)

    monkeypatch.setattr(retention_mod, "_limit_public_read", _deny)
    monkeypatch.setattr(retention_mod, "_cached_live_deals", lambda *_a, **_k: [])
    monkeypatch.setattr(retention_mod, "get_client_ip", lambda _r: "1.2.3.4")
    with pytest.raises(AppError):
        retention_mod.list_deals(MagicMock(), Response(), MagicMock(), limit=24)


@pytest.mark.asyncio
async def test_discovery_home_limiter_off_loop_and_overlapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _slow_limiter(*_a: Any, **_k: Any) -> None:
        time.sleep(0.15)  # blocking, like the Supabase RPC

    async def _slow_feed(*_a: Any, **_k: Any) -> Any:
        await asyncio.sleep(0.15)
        return _empty_home_payload()

    monkeypatch.setattr(discovery_mod, "_rate_limit_discovery_read", _slow_limiter)
    monkeypatch.setattr(discovery_mod, "build_home_feed", _slow_feed)

    ticks = 0

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker = asyncio.create_task(_ticker())
    response = Response()
    t0 = time.perf_counter()
    await discovery_mod.home_feed(
        MagicMock(),
        response,
        MagicMock(),
        department_paths=None,
        newest_limit=8,
        department_limit=4,
        services_limit=6,
        vendors_limit=6,
        trending_limit=8,
    )
    elapsed = time.perf_counter() - t0
    ticker.cancel()
    assert elapsed < 0.27, f"limiter and feed should overlap, took {elapsed:.3f}s"
    assert ticks >= 8, "event loop was blocked by the limiter"
    assert "s-maxage" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_home_cache_io_does_not_block_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    def _slow_get(*_a: Any, **_k: Any) -> None:
        time.sleep(0.1)

    monkeypatch.setattr(home_mod, "get_cached_json", _slow_get)
    monkeypatch.setattr(home_mod, "set_cached_json", lambda *_a, **_k: time.sleep(0.1))
    monkeypatch.setattr(home_mod, "list_catalog", lambda *_a, **_k: home_mod._empty_catalog())
    monkeypatch.setattr(
        home_mod, "build_browse_response", lambda *_a, **_k: type("R", (), {"items": []})()
    )
    monkeypatch.setattr(
        home_mod,
        "list_directory_vendors",
        lambda *_a, **_k: home_mod._empty_directory(page_size=6),
    )
    monkeypatch.setattr(home_mod, "fetch_trending_listings", lambda *_a, **_k: [])
    ticks = 0

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker = asyncio.create_task(_ticker())
    await home_mod.build_home_feed(MagicMock(), trending_limit=0)
    ticker.cancel()
    assert ticks >= 10


def test_candidate_build_is_single_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _MemCache()
    monkeypatch.setattr(catalog_mod, "get_cached_json", cache.get)
    monkeypatch.setattr(catalog_mod, "set_cached_json", cache.set)
    builds = {"n": 0}

    def _build(*_a: Any, **_k: Any) -> list[Any]:
        builds["n"] += 1
        time.sleep(0.1)
        return [POOL[0]]

    monkeypatch.setattr(catalog_mod, "_build_candidates", _build)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda _: catalog_mod._build_candidates_cached(MagicMock(), None), range(6))
        )
    assert builds["n"] == 1, "concurrent cold misses must share one build"
    assert all(len(r) == 1 for r in results)
