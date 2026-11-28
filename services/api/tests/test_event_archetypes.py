"""Event archetypes: derivation, per-archetype validation, safe reads."""

from __future__ import annotations

import pytest
from app.errors import AppError
from app.services.events.archetypes import (
    ARCHETYPES,
    CATEGORY_ARCHETYPE,
    derive_archetype,
    has_pending_sponsor,
    normalize_sponsors,
    prune_details,
    public_details,
    read_details,
    resolve_archetype,
    validate_details,
)


@pytest.mark.parametrize(
    ("category", "event_type", "expected"),
    [
        ("concerts", "single", "concert"),
        ("gospel", "single", "religious"),
        ("church", "single", "religious"),
        ("religious", "standard", "religious"),
        ("football", "single", "sports_family"),
        ("family", "single", "sports_family"),
        ("pop-up-dinners", "single", "restaurant"),
        ("private-events", "single", "private_gathering"),
        ("workshops", "private", "private_gathering"),
        ("workshops", "single", "generic"),
        (None, None, "generic"),
        ("unknown-slug", "standard", "generic"),
    ],
)
def test_derive_archetype(category: str | None, event_type: str | None, expected: str) -> None:
    assert derive_archetype(category, event_type) == expected


def test_category_map_only_targets_known_archetypes() -> None:
    assert set(CATEGORY_ARCHETYPE.values()) <= set(ARCHETYPES)
    assert "branded" not in ARCHETYPES


def test_resolve_prefers_override_and_ignores_junk() -> None:
    assert resolve_archetype("concert", "church") == ("concert", "override")
    assert resolve_archetype("branded", "church") == ("religious", "derived")
    assert resolve_archetype(None, "church") == ("religious", "derived")
    assert resolve_archetype("not-real", "church") == ("religious", "derived")


def test_concert_details_valid_and_normalised() -> None:
    out = validate_details(
        "concert",
        {
            "lineup": [{"name": "DJ Zed", "role": "dj", "slot": "21:30"}],
            "stages": ["Main"],
            "doors_open": "18:00",
            "sponsors": [{"name": "Mosi", "link_url": "https://example.com/mosi"}],
            "age_policy": "18_plus",
        },
    )
    assert out["lineup"][0]["slot"] == "21:30"
    assert out["sponsors"][0]["name"] == "Mosi"
    assert out["age_policy"] == "18_plus"


def test_religious_agenda_and_donation_note() -> None:
    out = validate_details(
        "religious",
        {
            "agenda": [{"time": "09:00", "title": "Worship", "speaker": "Pastor Jane"}],
            "donation_note": "Offerings welcome",
            "livestream_url": "https://example.com/live",
        },
    )
    assert out["agenda"][0]["title"] == "Worship"


def test_restaurant_menu_price_is_integer_ngwee() -> None:
    ok = validate_details(
        "restaurant",
        {
            "menu_sections": [
                {"title": "Mains", "items": [{"name": "Nshima", "price_ngwee": 12000}]}
            ]
        },
    )
    assert ok["menu_sections"][0]["items"][0]["price_ngwee"] == 12000
    for bad in (120.5, "12000", -1):
        with pytest.raises(AppError) as exc:
            validate_details(
                "restaurant",
                {"menu_sections": [{"title": "M", "items": [{"name": "x", "price_ngwee": bad}]}]},
            )
        assert exc.value.code == "invalid_archetype_details"
        assert exc.value.http_status == 422


def test_sports_family_age_groups_and_bounds() -> None:
    out = validate_details(
        "sports_family",
        {
            "age_groups": [{"label": "Kids", "min_age": 3, "max_age": 12}],
            "activities": [{"name": "Relay", "time": "10:15"}],
            "bring_list": ["Water"],
        },
    )
    assert out["age_groups"][0]["max_age"] == 12
    with pytest.raises(AppError):
        validate_details("sports_family", {"age_groups": [{"label": "x", "min_age": -1}]})
    with pytest.raises(AppError):
        validate_details("sports_family", {"activities": [{"name": "x"}] * 21})


def test_sponsor_status_is_server_controlled() -> None:
    sponsor = {"name": "Mosi", "logo": "sponsors/mosi", "status": "approved"}
    fresh = normalize_sponsors(validate_details("concert", {"sponsors": [sponsor]}), None)
    assert fresh["sponsors"][0]["status"] == "pending"  # client status ignored
    stored = {"sponsors": [{**sponsor, "status": "approved"}]}
    same = normalize_sponsors(validate_details("concert", {"sponsors": [sponsor]}), stored)
    assert same["sponsors"][0]["status"] == "approved"  # unchanged keeps status
    edited = {**sponsor, "link_url": "https://mosi.example/new"}
    changed = normalize_sponsors(validate_details("concert", {"sponsors": [edited]}), stored)
    assert changed["sponsors"][0]["status"] == "pending"  # edit requires re-review
    assert has_pending_sponsor(changed)
    assert not has_pending_sponsor(same)


def test_public_details_show_approved_sponsors_only() -> None:
    raw = {
        "stages": ["Main"],
        "sponsors": [
            {"name": "A", "status": "approved"},
            {"name": "B", "status": "pending"},
            {"name": "C", "status": "rejected"},
            {"name": "D"},
        ],
    }
    out = public_details("concert", raw)
    assert [s["name"] for s in out["sponsors"]] == ["A"]
    assert out["stages"] == ["Main"]
    none = public_details("concert", {"sponsors": [{"name": "B", "status": "pending"}]})
    assert "sponsors" not in none


def test_sponsors_allowed_on_every_archetype() -> None:
    for archetype in ARCHETYPES:
        assert validate_details(archetype, {"sponsors": [{"name": "Mosi"}]})["sponsors"]


def test_private_gathering_and_generic() -> None:
    assert validate_details("private_gathering", {"host_names": "Mr and Mrs Banda"})
    assert validate_details("generic", {"agenda": [{"time": "10:00", "title": "Start"}]})


def test_unknown_keys_forbidden_per_archetype() -> None:
    # lineup belongs to concert, not religious
    with pytest.raises(AppError) as exc:
        validate_details("religious", {"lineup": []})
    assert exc.value.details["field"] == "archetype_details"


@pytest.mark.parametrize(
    "payload",
    [
        {"sponsors": [{"name": "x", "link_url": "javascript:alert(1)"}]},
        {"sponsors": [{"name": "x", "link_url": "http://example.com"}]},
        {"sponsors": [{"name": "x", "logo": "data:image/png;base64,AAAA"}]},
        {"sponsors": [{"name": "x", "logo": "../../etc/passwd"}]},
        {"sponsors": [{"name": str(i)} for i in range(7)]},
        {"faqs": [{"question": "q", "answer": "a"}] * 9},
        {"dress_code": "x" * 81},
        {"age_policy": "21_plus"},
    ],
)
def test_common_field_rejections(payload: dict[str, object]) -> None:
    with pytest.raises(AppError):
        validate_details("generic", payload)


def test_time_format_enforced() -> None:
    with pytest.raises(AppError):
        validate_details("concert", {"doors_open": "25:00"})
    with pytest.raises(AppError):
        validate_details("concert", {"doors_open": "7pm"})


def test_non_object_rejected_and_none_is_empty() -> None:
    assert validate_details("concert", None) == {}
    with pytest.raises(AppError):
        validate_details("concert", ["x"])


def test_total_size_cap() -> None:
    big = {
        "lineup": [
            {"name": "n" * 80, "bio": "b" * 200, "stage": "s" * 60, "image": "i" * 200}
            for _ in range(30)
        ]
    }
    with pytest.raises(AppError):
        validate_details("concert", big)


def test_prune_drops_foreign_keys_when_archetype_changes() -> None:
    stored = {"lineup": [{"name": "A"}], "dress_code": "Smart", "sponsors": []}
    assert prune_details("religious", stored) == {"dress_code": "Smart"}


def test_read_details_degrades_to_empty_on_junk() -> None:
    assert read_details("concert", {"lineup": "not-a-list"}) == {}
    assert read_details("concert", {"sponsors": [{"name": "x", "link_url": "javascript:1"}]}) == {}
    assert read_details("concert", None) == {}
    assert read_details("concert", {"stages": ["Main"]}) == {"stages": ["Main"]}
