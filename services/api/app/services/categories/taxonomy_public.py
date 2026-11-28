"""Cached public service/event taxonomy reads for the customer menu and vendor pickers."""

from __future__ import annotations

from typing import Any

from app.core.ttl_cache import get_cached_json, set_cached_json
from app.services.categories.taxonomy import Audience, TaxonomyNode, load_public_nodes

TTL_SECONDS = 300
_KEY = "public:taxonomy:v1:{umbrella}:{audience}"
_UMBRELLAS = ("service", "event")
_AUDIENCES = ("customer", "vendor")


def list_public(
    client: Any, umbrella: str, audience: Audience, *, use_cache: bool = True
) -> list[TaxonomyNode]:
    key = _KEY.format(umbrella=umbrella, audience=audience)
    if use_cache:
        cached = get_cached_json(key)
        if isinstance(cached, list):
            try:
                return [TaxonomyNode.model_validate(item) for item in cached]
            except Exception:  # noqa: BLE001
                pass
    nodes = load_public_nodes(client, umbrella, audience)
    if use_cache:
        set_cached_json(key, [n.model_dump(mode="json") for n in nodes], ttl_seconds=TTL_SECONDS)
    return nodes


def invalidate() -> None:
    for umbrella in _UMBRELLAS:
        for audience in _AUDIENCES:
            set_cached_json(
                _KEY.format(umbrella=umbrella, audience=audience),
                {"stale": True},
                ttl_seconds=1,
            )
