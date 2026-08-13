"""Vendor role grant is tied to KYC approval, not signup or draft onboarding."""

from __future__ import annotations

from typing import Any

import pytest
from app.errors import AppError
from app.services.kyc.state_machine import (
    transition_approve,
    transition_reject,
    transition_revoke,
    transition_submit,
    transition_suspend,
)
from app.services.kyc.vendor_role import ensure_vendor_owner_role

OWNER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
STRANGER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ADMIN = "66666666-6666-6666-6666-666666666666"
VENDOR_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
KYC_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, store: dict[str, list[dict[str, Any]]], table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, Any]] = []
        self._mode = "select"
        self._payload: dict[str, Any] | None = None
        self._maybe_single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, _columns: str) -> _FakeQuery:
        self._mode = "select"
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append((column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> _FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> _FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> _FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        self._mode = "insert"
        self._payload = dict(row)
        if "id" not in self._payload:
            self._payload["id"] = f"generated-{len(self._store.setdefault(self._table, []))}"
        return self

    def update(self, patch: dict[str, Any]) -> _FakeQuery:
        self._mode = "update"
        self._payload = dict(patch)
        return self

    def upsert(
        self,
        row: dict[str, Any] | list[dict[str, Any]],
        on_conflict: str | None = None,
    ) -> _FakeQuery:
        self._mode = "upsert"
        self._payload = dict(row if isinstance(row, dict) else row[0])
        self._on_conflict = on_conflict
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        return all(str(row.get(col)) == str(val) for col, val in self._filters)

    def execute(self) -> _FakeResponse:
        rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            assert self._payload is not None
            inserted = dict(self._payload)
            rows.append(inserted)
            return _FakeResponse([inserted])
        if self._mode == "upsert":
            assert self._payload is not None
            keys = [part.strip() for part in (self._on_conflict or "user_id,role").split(",")]
            for existing in rows:
                if all(str(existing.get(key)) == str(self._payload.get(key)) for key in keys):
                    return _FakeResponse([existing])
            inserted = dict(self._payload)
            rows.append(inserted)
            return _FakeResponse([inserted])
        if self._mode == "update":
            assert self._payload is not None
            updated: list[dict[str, Any]] = []
            for row in rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return _FakeResponse(updated)
        selected = [dict(row) for row in rows if self._matches(row)]
        if self._order is not None:
            column, desc = self._order
            selected.sort(key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._limit is not None:
            selected = selected[: self._limit]
        if self._maybe_single:
            return _FakeResponse(selected[0] if selected else None)
        return _FakeResponse(selected)


class _FakeClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self._store = store

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._store, name)

    def rpc(self, fn: str, params: dict[str, Any]) -> _FakeRpc:
        return _FakeRpc(self._store, fn, params)


class _FakeRpc:
    def __init__(
        self, store: dict[str, list[dict[str, Any]]], fn: str, params: dict[str, Any]
    ) -> None:
        self._store = store
        self._fn = fn
        self._params = params
        self._client = _RpcStoreAdapter(store)

    def execute(self) -> _FakeResponse:
        if self._fn == "approve_kyc_vendor":
            from tests.helpers.fake_approve_kyc_rpc import fake_approve_kyc_vendor

            return _FakeResponse(fake_approve_kyc_vendor(self._client, self._params))
        raise NotImplementedError(f"rpc {self._fn} is not implemented in fake client")


class _RpcStoreAdapter:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self._store = store
        self._block_vendor_role_grant = bool(store.get("_block_vendor_role_grant"))

    def table(self, name: str) -> _FakeTableAdapter:
        return _FakeTableAdapter(self._store, name)


class _FakeTableAdapter:
    def __init__(self, store: dict[str, list[dict[str, Any]]], name: str) -> None:
        self.rows = store.setdefault(name, [])


class _Wrapper:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self.client = _FakeClient(store)
        self.store = store


def _store(
    *,
    vendor_status: str = "pending_kyc",
    kyc_status: str = "submitted",
    owner: str = OWNER,
    extra_roles: list[dict[str, str]] | None = None,
    kyc_tier: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    roles = [{"user_id": owner, "role": "customer"}]
    if extra_roles:
        roles.extend(extra_roles)
    return {
        "vendors": [
            {
                "id": VENDOR_ID,
                "owner_user_id": owner,
                "status": vendor_status,
                "kyc_tier": kyc_tier,
            }
        ],
        "kyc_records": [
            {
                "id": KYC_ID,
                "vendor_id": VENDOR_ID,
                "tier": 2,
                "status": kyc_status,
                "doc_storage_paths": [],
                "momo_name_match": {"matched": True},
                "reviewer_notes": None,
                "reviewed_by": None,
                "reviewed_at": None,
                "decision_reason": None,
                "lifecycle_reason": None,
            }
        ],
        "user_roles": roles,
        "audit_log": [],
    }


def _roles_for(store: dict[str, list[dict[str, Any]]], user_id: str) -> list[str]:
    return sorted(
        str(row["role"]) for row in store["user_roles"] if str(row["user_id"]) == user_id
    )


def test_signup_customer_only_has_no_vendor_role() -> None:
    store = _store(vendor_status="draft", kyc_status="submitted")
    store["vendors"] = []
    store["kyc_records"] = []
    assert _roles_for(store, OWNER) == ["customer"]


def test_draft_vendor_does_not_grant_role() -> None:
    wrapper = _Wrapper(_store(vendor_status="draft"))
    with pytest.raises(AppError) as exc:
        ensure_vendor_owner_role(wrapper, owner_user_id=OWNER, vendor_id=VENDOR_ID)
    assert exc.value.code == "vendor_role_vendor_not_active"
    assert _roles_for(wrapper.store, OWNER) == ["customer"]


def test_submitted_kyc_does_not_grant_role() -> None:
    wrapper = _Wrapper(_store(vendor_status="pending_kyc", kyc_status="submitted"))
    with pytest.raises(AppError) as exc:
        ensure_vendor_owner_role(wrapper, owner_user_id=OWNER, vendor_id=VENDOR_ID)
    assert exc.value.code == "vendor_role_vendor_not_active"
    assert "vendor" not in _roles_for(wrapper.store, OWNER)


def test_approve_grants_vendor_role_exactly_once() -> None:
    wrapper = _Wrapper(_store())
    result = transition_approve(
        actor_id=ADMIN,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        tier=2,
        service_client=wrapper,
    )
    assert result["vendor"]["status"] == "active"
    assert result["vendor_role"]["outcome"] == "granted"
    assert result["vendor_role"]["user_id"] == OWNER
    assert _roles_for(wrapper.store, OWNER) == ["customer", "vendor"]
    vendor_roles = [
        row
        for row in wrapper.store["user_roles"]
        if row["user_id"] == OWNER and row["role"] == "vendor"
    ]
    assert len(vendor_roles) == 1
    assert wrapper.store["audit_log"][0]["action"] == "kyc.approve"
    assert wrapper.store["audit_log"][0]["after"]["vendor_role"]["outcome"] == "granted"


def test_repeated_ensure_is_idempotent() -> None:
    wrapper = _Wrapper(_store(vendor_status="active", kyc_status="approved", kyc_tier=2))
    first = ensure_vendor_owner_role(wrapper, owner_user_id=OWNER, vendor_id=VENDOR_ID)
    second = ensure_vendor_owner_role(wrapper, owner_user_id=OWNER, vendor_id=VENDOR_ID)
    assert first["outcome"] == "granted"
    assert second["outcome"] == "already_present"
    assert (
        len(
            [
                row
                for row in wrapper.store["user_roles"]
                if row["role"] == "vendor" and row["user_id"] == OWNER
            ]
        )
        == 1
    )


def test_wrong_owner_cannot_receive_role() -> None:
    wrapper = _Wrapper(_store(vendor_status="active", kyc_status="approved", kyc_tier=2))
    with pytest.raises(AppError) as exc:
        ensure_vendor_owner_role(wrapper, owner_user_id=STRANGER, vendor_id=VENDOR_ID)
    assert exc.value.code == "vendor_role_owner_mismatch"
    assert "vendor" not in _roles_for(wrapper.store, STRANGER)
    assert "vendor" not in _roles_for(wrapper.store, OWNER)


def test_unrelated_user_cannot_receive_role() -> None:
    wrapper = _Wrapper(
        _store(
            vendor_status="active",
            extra_roles=[{"user_id": STRANGER, "role": "customer"}],
        )
    )
    wrapper.store["vendors"][0]["status"] = "active"
    with pytest.raises(AppError):
        ensure_vendor_owner_role(wrapper, owner_user_id=STRANGER, vendor_id=VENDOR_ID)
    assert _roles_for(wrapper.store, STRANGER) == ["customer"]


def test_rejected_vendor_does_not_gain_role() -> None:
    wrapper = _Wrapper(_store())
    transition_reject(
        actor_id=ADMIN,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        reviewer_notes="docs unclear",
        service_client=wrapper,
    )
    assert wrapper.store["kyc_records"][0]["status"] == "rejected"
    assert wrapper.store["vendors"][0]["status"] == "pending_kyc"
    assert "vendor" not in _roles_for(wrapper.store, OWNER)


def test_submit_does_not_grant_role() -> None:
    wrapper = _Wrapper(_store(vendor_status="draft", kyc_status="submitted"))
    wrapper.store["kyc_records"] = []
    transition_submit(
        actor_id=OWNER,
        vendor_id=VENDOR_ID,
        tier=2,
        doc_storage_paths=["kyc/a.png"],
        momo_name_match={"matched": True},
        service_client=wrapper,
    )
    assert wrapper.store["vendors"][0]["status"] == "pending_kyc"
    assert "vendor" not in _roles_for(wrapper.store, OWNER)


def test_suspend_keeps_vendor_role() -> None:
    wrapper = _Wrapper(
        _store(
            vendor_status="active",
            kyc_status="approved",
            kyc_tier=2,
            extra_roles=[{"user_id": OWNER, "role": "vendor"}],
        )
    )
    transition_suspend(
        actor_id=ADMIN,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        reason="compliance hold",
        service_client=wrapper,
    )
    assert wrapper.store["vendors"][0]["status"] == "suspended"
    assert "vendor" in _roles_for(wrapper.store, OWNER)


def test_reactivation_via_reapprove_is_idempotent() -> None:
    wrapper = _Wrapper(
        _store(
            vendor_status="pending_kyc",
            kyc_status="submitted",
            extra_roles=[{"user_id": OWNER, "role": "vendor"}],
        )
    )
    result = transition_approve(
        actor_id=ADMIN,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        tier=2,
        service_client=wrapper,
    )
    assert result["vendor"]["status"] == "active"
    assert result["vendor_role"]["outcome"] == "already_present"
    assert (
        len(
            [
                row
                for row in wrapper.store["user_roles"]
                if row["user_id"] == OWNER and row["role"] == "vendor"
            ]
        )
        == 1
    )


def test_grant_failure_rolls_back_active_vendor() -> None:
    wrapper = _Wrapper(_store())
    wrapper.store["_block_vendor_role_grant"] = True  # type: ignore[assignment]

    with pytest.raises(AppError) as exc:
        transition_approve(
            actor_id=ADMIN,
            vendor_id=VENDOR_ID,
            kyc_record_id=KYC_ID,
            tier=2,
            service_client=wrapper,
        )
    assert exc.value.code == "vendor_role_grant_failed"
    assert wrapper.store["vendors"][0]["status"] == "pending_kyc"
    assert wrapper.store["kyc_records"][0]["status"] == "submitted"
    assert "vendor" not in _roles_for(wrapper.store, OWNER)
    assert wrapper.store["audit_log"] == []


def test_revoke_keeps_vendor_role() -> None:
    wrapper = _Wrapper(
        _store(
            vendor_status="active",
            kyc_status="approved",
            kyc_tier=2,
            extra_roles=[{"user_id": OWNER, "role": "vendor"}],
        )
    )
    transition_revoke(
        actor_id=ADMIN,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        reason="licence withdrawn",
        service_client=wrapper,
    )
    assert wrapper.store["vendors"][0]["status"] == "draft"
    assert "vendor" in _roles_for(wrapper.store, OWNER)


def test_admin_roles_are_untouched() -> None:
    wrapper = _Wrapper(
        _store(
            extra_roles=[
                {"user_id": ADMIN, "role": "admin"},
                {"user_id": ADMIN, "role": "customer"},
            ]
        )
    )
    transition_approve(
        actor_id=ADMIN,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        tier=2,
        service_client=wrapper,
    )
    assert _roles_for(wrapper.store, ADMIN) == ["admin", "customer"]
    assert "vendor" not in _roles_for(wrapper.store, ADMIN)
