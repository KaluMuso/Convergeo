"""Landmark keyword matcher for Lusaka delivery bands (no GPS), plus the Band B fallback seed."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.routers.checkout import (
    FALLBACK_DELIVERY_ZONE_KEY,
    _load_fallback_delivery_zone,
    resolve_delivery_zone,
)

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20261113060000_delivery_fallback_zone_band_b.sql"
)
ZONES: dict[str, dict[str, Any]] = {
    "lusaka_a": {"zone_key": "lusaka_a"},
    "lusaka_b": {"zone_key": "lusaka_b"},
    "lusaka_c": {"zone_key": "lusaka_c"},
}


def _zone(landmark: str | None, lat: float | None = None, lng: float | None = None) -> str | None:
    return resolve_delivery_zone(lat=lat, lng=lng, landmark=landmark)


@pytest.mark.parametrize(
    ("landmark", "expected"),
    [
        ("Kabulonga, Lusaka", "lusaka_a"),
        ("Cairo Road, Lusaka", "lusaka_a"),
        ("near Manda Hill", "lusaka_a"),
        ("Rhodes Park", "lusaka_a"),
        ("Levy Junction", "lusaka_a"),
        ("UNZA main gate", "lusaka_a"),
        ("Chilenje South", "lusaka_b"),
        ("Matero, Lusaka", "lusaka_b"),
        ("Ng'ombe compound", "lusaka_b"),
        ("Ngombe", "lusaka_b"),
        ("Ibex Hill road", "lusaka_b"),
        ("Chalala", "lusaka_c"),
        ("KKIA airport", "lusaka_c"),
        ("Leopard's Hill Road", "lusaka_c"),
        ("Kafue Road, Lusaka", "lusaka_c"),
        ("Band C please", "lusaka_c"),
        ("Woodlands Stage 2", "lusaka_a"),
    ],
)
def test_keyword_mapping_per_band(landmark: str, expected: str) -> None:
    assert _zone(landmark) == expected


@pytest.mark.parametrize(
    "landmark",
    ["Romance Street", "Rome", "Truth Lane", "Smithfield", "Roadside Garden", "Levy Plaza"],
)
def test_keywords_match_whole_words_only(landmark: str) -> None:
    # "roma", "uth", "levy" and "garden" must not match inside other words.
    assert _zone(landmark) is None


def test_longest_phrase_wins_over_lusaka_and_shorter_area() -> None:
    assert _zone("Matero, Lusaka") == "lusaka_b"
    assert _zone("Kafue Road near Chilanga") == "lusaka_c"


def test_explicit_band_words_beat_area_names() -> None:
    assert _zone("Band B, Kabulonga") == "lusaka_b"


def test_gps_wins_over_keywords() -> None:
    # Chalala is a Band C keyword, but a GPS fix at the CBD is Band A.
    assert _zone("Chalala", lat=-15.4167, lng=28.2833) == "lusaka_a"
    # GPS outside every band is refused even when a keyword would match.
    assert _zone("Kabulonga", lat=-12.97, lng=28.63) is None


def test_other_towns_still_refused() -> None:
    assert _zone("Kitwe, Chilenje") is None


def test_unknown_landmark_has_no_keyword_zone() -> None:
    assert _zone("Plot 12, behind the blue gate") is None


def _config_service(value: Any) -> MagicMock:
    service = MagicMock()
    chain = service.client.table.return_value.select.return_value.eq.return_value
    chain.maybe_single.return_value.execute.return_value = MagicMock(data={"value": value})
    return service


def test_migration_seeds_lusaka_b_in_the_encoding_the_code_reads() -> None:
    sql = MIGRATION.read_text()
    assert f"'{FALLBACK_DELIVERY_ZONE_KEY}'" in sql
    literal = re.search(r"'(\"[a-z_]+\")'::jsonb", sql)
    assert literal is not None
    seeded = json.loads(literal.group(1))
    assert seeded == "lusaka_b"
    assert _load_fallback_delivery_zone(_config_service(seeded), ZONES) == "lusaka_b"
    assert "delete from public.platform_config" in sql
