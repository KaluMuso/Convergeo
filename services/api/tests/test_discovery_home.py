"""Concurrency / partial-failure tests for the homepage discovery BFF."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.routers.catalog import CatalogListResponse, FacetCounts
from app.routers.directory import DirectoryFacets, DirectoryListResponse
from app.services.discovery import home as home_mod
from app.services.discovery.home import SECTION_TIMEOUT_SECONDS, build_home_feed


def _empty_catalog() -> CatalogListResponse:
    return CatalogListResponse(items=[], facets=FacetCounts(), total=0, next_cursor=None)


def _empty_directory() -> DirectoryListResponse:
    return DirectoryListResponse(
        items=[],
        facets=DirectoryFacets(),
        total=0,
        page=1,
        page_size=6,
    )


@pytest.mark.asyncio
async def test_home_feed_fans_out_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each sync section sleeps ~80ms; wall time must be << serial sum."""

    def _slow_catalog(*_a: Any, **_k: Any) -> CatalogListResponse:
        time.sleep(0.08)
        return _empty_catalog()

    def _slow_services(*_a: Any, **_k: Any) -> Any:
        time.sleep(0.08)

        class _Resp:
            items: list[Any] = []

        return _Resp()

    def _slow_vendors(*_a: Any, **_k: Any) -> DirectoryListResponse:
        time.sleep(0.08)
        return _empty_directory()

    monkeypatch.setattr(home_mod, "list_catalog", _slow_catalog)
    monkeypatch.setattr(home_mod, "build_browse_response", _slow_services)
    monkeypatch.setattr(home_mod, "list_directory_vendors", _slow_vendors)
    monkeypatch.setattr(home_mod, "fetch_trending_listings", lambda *_a, **_k: [])
    monkeypatch.setattr(home_mod, "get_cached_json", lambda *_a, **_k: None)
    monkeypatch.setattr(home_mod, "set_cached_json", lambda *_a, **_k: None)

    t0 = time.perf_counter()
    payload = await build_home_feed(
        MagicMock(),
        department_paths=["electronics", "fashion"],
        trending_limit=0,
        use_cache=False,
    )
    elapsed = time.perf_counter() - t0

    # 3 primary + 2 department = 5 × 80ms serial ≈ 400ms; concurrent ≪ that.
    assert elapsed < 0.28, f"expected concurrent fan-in, took {elapsed:.3f}s"
    assert payload.newest.total == 0
    assert payload.services == []
    assert payload.vendors.total == 0


@pytest.mark.asyncio
async def test_home_feed_partial_failure_omits_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _ok_catalog(*_a: Any, **_k: Any) -> CatalogListResponse:
        return CatalogListResponse(
            items=[],
            facets=FacetCounts(),
            total=0,
            next_cursor=None,
        )

    def _boom_services(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("services down")

    monkeypatch.setattr(home_mod, "list_catalog", _ok_catalog)
    monkeypatch.setattr(home_mod, "build_browse_response", _boom_services)
    monkeypatch.setattr(home_mod, "list_directory_vendors", lambda *_a, **_k: _empty_directory())
    monkeypatch.setattr(home_mod, "fetch_trending_listings", lambda *_a, **_k: [])
    monkeypatch.setattr(home_mod, "get_cached_json", lambda *_a, **_k: None)
    monkeypatch.setattr(home_mod, "set_cached_json", lambda *_a, **_k: None)

    payload = await build_home_feed(
        MagicMock(),
        department_paths=[],
        trending_limit=0,
        use_cache=False,
    )
    assert payload.services == []
    assert payload.vendors.page_size == 6


@pytest.mark.asyncio
async def test_home_feed_section_timeout_returns_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _hang(*_a: Any, **_k: Any) -> CatalogListResponse:
        time.sleep(SECTION_TIMEOUT_SECONDS + 1.5)
        return _empty_catalog()

    monkeypatch.setattr(home_mod, "list_catalog", _hang)
    monkeypatch.setattr(
        home_mod,
        "build_browse_response",
        lambda *_a, **_k: type("R", (), {"items": []})(),
    )
    monkeypatch.setattr(home_mod, "list_directory_vendors", lambda *_a, **_k: _empty_directory())
    monkeypatch.setattr(home_mod, "fetch_trending_listings", lambda *_a, **_k: [])
    monkeypatch.setattr(home_mod, "get_cached_json", lambda *_a, **_k: None)
    monkeypatch.setattr(home_mod, "set_cached_json", lambda *_a, **_k: None)

    async def _fast_section(label: str, fn: Any, *, fallback: Any, timeout: float = 0.05) -> Any:
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout)
        except Exception:
            return fallback

    monkeypatch.setattr(home_mod, "_run_section", _fast_section)

    t0 = time.perf_counter()
    payload = await build_home_feed(
        MagicMock(),
        department_paths=[],
        trending_limit=0,
        use_cache=False,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0
    assert payload.newest.items == []
