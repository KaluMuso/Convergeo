"""Unit tests for the DPA data-export purge core (injected list/remove fakes)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.privacy.export_purge import (
    EXPORT_PATH_PREFIX,
    StoredObject,
    purge_export_bundles,
    select_expired,
)

_NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def _obj(name: str, age_hours: float) -> StoredObject:
    return StoredObject(name=name, created_at=_NOW - timedelta(hours=age_hours))


def test_select_expired_returns_only_aged_export_objects() -> None:
    objects = [
        _obj(f"{EXPORT_PATH_PREFIX}/u1/old.json", age_hours=48),
        _obj(f"{EXPORT_PATH_PREFIX}/u1/fresh.json", age_hours=1),
        _obj(f"{EXPORT_PATH_PREFIX}/u2/edge.json", age_hours=24.5),
    ]
    expired = select_expired(objects, now=_NOW, ttl_hours=24)
    assert set(expired) == {
        f"{EXPORT_PATH_PREFIX}/u1/old.json",
        f"{EXPORT_PATH_PREFIX}/u2/edge.json",
    }


def test_select_expired_scope_guard_never_leaves_the_prefix() -> None:
    # An object outside data-exports/ must never be selected for deletion, even if aged.
    objects = [
        _obj("kyc-docs/u1/passport.jpg", age_hours=999),
        _obj("order-evidence/o1/photo.jpg", age_hours=999),
        _obj(f"{EXPORT_PATH_PREFIX}/u1/old.json", age_hours=999),
    ]
    expired = select_expired(objects, now=_NOW, ttl_hours=24)
    assert expired == [f"{EXPORT_PATH_PREFIX}/u1/old.json"]


def test_purge_deletes_expired_and_is_idempotent() -> None:
    removed: list[list[str]] = []
    aged = [
        _obj(f"{EXPORT_PATH_PREFIX}/u1/old.json", age_hours=48),
        _obj(f"{EXPORT_PATH_PREFIX}/u1/fresh.json", age_hours=1),
    ]

    first = purge_export_bundles(
        list_objects=lambda: aged,
        remove_objects=removed.append,
        now=_NOW,
        ttl_hours=24,
    )
    assert first.scanned == 2
    assert first.deleted == 1
    assert removed == [[f"{EXPORT_PATH_PREFIX}/u1/old.json"]]

    # Second run over only fresh objects removes nothing (idempotent) — no remove call.
    removed.clear()
    second = purge_export_bundles(
        list_objects=lambda: [_obj(f"{EXPORT_PATH_PREFIX}/u1/fresh.json", age_hours=1)],
        remove_objects=removed.append,
        now=_NOW,
        ttl_hours=24,
    )
    assert second.deleted == 0
    assert removed == []


def test_purge_empty_bucket_is_a_noop() -> None:
    calls: list[list[str]] = []
    result = purge_export_bundles(
        list_objects=list,
        remove_objects=calls.append,
        now=_NOW,
        ttl_hours=24,
    )
    assert result == result.__class__(scanned=0, deleted=0)
    assert calls == []
