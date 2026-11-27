"""Regression guard: blocking customer/admin handlers must stay sync (threadpool)."""

from __future__ import annotations

import importlib
import inspect

import pytest
from fastapi import APIRouter

_MODULES = [
    "account",
    "cart",
    "cart_tickets",
    "contacts",
    "follows",
    "quotes",
    "admin_base",
    "admin_branches",
    "admin_business",
    "admin_clip_analytics",
    "admin_clip_pilot",
    "admin_clips",
    "admin_config",
    "admin_dashboards",
    "admin_extras",
    "admin_flags",
    "admin_governance",
    "admin_intake",
    "admin_kyc",
    "admin_merch",
    "admin_products",
    "admin_search_insights",
    "admin_support",
    "admin_vendor_plans",
    "admin_vendors",
]

# Spot checks: these only make blocking Supabase calls and must be plain `def`.
_MUST_BE_SYNC = {
    "account": ["get_wishlist", "put_wishlist", "get_recently_viewed"],
    "cart": ["add_cart_item", "merge_cart_on_login"],
    "contacts": ["get_my_handle", "get_my_qr"],
}


@pytest.mark.parametrize("module_name", _MODULES)
def test_async_endpoints_actually_await(module_name: str) -> None:
    module = importlib.import_module(f"app.routers.{module_name}")
    routers = [v for v in vars(module).values() if isinstance(v, APIRouter)]
    assert routers, module_name
    routes = [r for router in routers for r in router.routes]
    for route in routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or not inspect.iscoroutinefunction(endpoint):
            continue
        source = inspect.getsource(endpoint)
        assert "await " in source or "async with" in source or "async for" in source, (
            f"{module_name}.{endpoint.__name__} is async without awaiting; make it a sync def"
        )


@pytest.mark.parametrize(
    ("module_name", "names"), sorted(_MUST_BE_SYNC.items()), ids=lambda v: str(v)
)
def test_converted_endpoints_are_not_coroutines(module_name: str, names: list[str]) -> None:
    module = importlib.import_module(f"app.routers.{module_name}")
    for name in names:
        assert not inspect.iscoroutinefunction(getattr(module, name)), name
