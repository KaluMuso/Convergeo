"""app.staging.auth_personas — Supabase Auth Admin API persona provisioning.

Unit-level: mocks the Admin API surface (`client.auth.admin.*`) rather than a
real GoTrue service — no CI job runs a real Supabase Auth server, and this is
exactly the codebase's existing convention for testing `.auth.admin.*`
callers (see tests around app/services/identity.py, app/routers/privacy.py).

These tests prove the decision logic that replaces the old raw
`INSERT INTO auth.users` seed path: create when missing, recreate when a
legacy row has zero identities (the exact proven-bad state:
`auth.identities count=0` despite `auth.users` existing), repair confirmation
when needed, no-op when already correct, touch only the fixed persona ids
ever, and fail closed on any Admin API error.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from app.staging.auth_personas import AuthPersonaError, ensure_auth_personas, verify_auth_personas


@dataclass(frozen=True, slots=True)
class _FakePersona:
    key: str
    user_id: str
    phone: str
    email: str
    handle: str


CUSTOMER = _FakePersona(
    key="CUSTOMER_A",
    user_id="a1000000-0000-4000-8000-000000000001",
    phone="+260970000001",
    email="stg-rv-20260719-cust-01@staging.vergeo5.test",
    handle="stg-rv-20260719-cust-01",
)
VENDOR = _FakePersona(
    key="APPROVED_VENDOR_A",
    user_id="a1000000-0000-4000-8000-000000000004",
    phone="+260970000004",
    email="stg-rv-20260719-vend-apr@staging.vergeo5.test",
    handle="stg-rv-20260719-vend-apr",
)
UNRELATED_REAL_USER_ID = "99999999-0000-4000-8000-000000000099"


class _Identity:
    def __init__(self, provider: str, user_id: str) -> None:
        self.provider = provider
        self.user_id = user_id


class _User:
    def __init__(
        self, *, id: str, phone_confirmed_at: str | None, identities: list[_Identity]
    ) -> None:
        self.id = id
        self.phone_confirmed_at = phone_confirmed_at
        self.identities = identities


class _AdminApiError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"admin api error {status}")
        self.status = status


class FakeAdminApi:
    """In-memory stand-in for client.auth.admin — records every call so
    tests can assert exactly which ids were ever touched."""

    def __init__(self, seed_users: dict[str, _User] | None = None) -> None:
        self.users: dict[str, _User] = dict(seed_users or {})
        self.calls: list[tuple[str, str]] = []

    def get_user_by_id(self, uid: str) -> Any:
        self.calls.append(("get", uid))
        user = self.users.get(uid)
        if user is None:
            raise _AdminApiError(status=404)
        return SimpleNamespace(user=user)

    def create_user(self, attributes: dict[str, Any]) -> Any:
        uid = attributes["id"]
        self.calls.append(("create", uid))
        user = _User(
            id=uid,
            phone_confirmed_at="2026-01-01T00:00:00Z",
            identities=[_Identity("phone", uid)],
        )
        self.users[uid] = user
        return SimpleNamespace(user=user)

    def delete_user(self, uid: str, should_soft_delete: bool = False) -> None:
        self.calls.append(("delete", uid))
        self.users.pop(uid, None)

    def update_user_by_id(self, uid: str, attributes: dict[str, Any]) -> Any:
        self.calls.append(("update", uid))
        user = self.users[uid]
        user.phone_confirmed_at = "2026-01-01T00:00:00Z"
        return SimpleNamespace(user=user)


class FakeClient:
    def __init__(self, admin: FakeAdminApi) -> None:
        self.auth = SimpleNamespace(admin=admin)


class TestEnsureAuthPersonas:
    def test_creates_missing_persona(self) -> None:
        admin = FakeAdminApi()
        client = FakeClient(admin)

        outcomes = ensure_auth_personas(client, personas=(CUSTOMER,))

        assert outcomes == {"CUSTOMER_A": "created"}
        assert ("create", CUSTOMER.user_id) in admin.calls

    def test_created_persona_has_deterministic_uuid_and_owned_phone_identity(self) -> None:
        admin = FakeAdminApi()
        client = FakeClient(admin)

        ensure_auth_personas(client, personas=(CUSTOMER,))

        user = admin.users[CUSTOMER.user_id]
        assert user.id == CUSTOMER.user_id
        assert user.phone_confirmed_at is not None
        assert any(
            identity.provider == "phone" and identity.user_id == CUSTOMER.user_id
            for identity in user.identities
        )

    def test_no_op_when_already_correct(self) -> None:
        admin = FakeAdminApi(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id,
                    phone_confirmed_at="2026-01-01T00:00:00Z",
                    identities=[_Identity("phone", CUSTOMER.user_id)],
                )
            }
        )
        client = FakeClient(admin)

        outcomes = ensure_auth_personas(client, personas=(CUSTOMER,))

        assert outcomes == {"CUSTOMER_A": "already-ok"}
        assert admin.calls == [("get", CUSTOMER.user_id)]
        assert ("create", CUSTOMER.user_id) not in admin.calls
        assert ("delete", CUSTOMER.user_id) not in admin.calls
        assert ("update", CUSTOMER.user_id) not in admin.calls

    def test_repairs_confirmation_when_identity_exists_but_unconfirmed(self) -> None:
        admin = FakeAdminApi(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id,
                    phone_confirmed_at=None,
                    identities=[_Identity("phone", CUSTOMER.user_id)],
                )
            }
        )
        client = FakeClient(admin)

        outcomes = ensure_auth_personas(client, personas=(CUSTOMER,))

        assert outcomes == {"CUSTOMER_A": "repaired-confirmation"}
        assert ("update", CUSTOMER.user_id) in admin.calls
        assert ("create", CUSTOMER.user_id) not in admin.calls
        assert ("delete", CUSTOMER.user_id) not in admin.calls

    def test_recreates_legacy_row_with_zero_identities(self) -> None:
        """The exact proven-bad state: auth.users exists (raw SQL era),
        phone_confirmed_at is even set, but auth.identities is empty — GoTrue
        still rejects OTP with 422 otp_disabled. Must delete then recreate,
        in that order, never merely patch it in place."""
        admin = FakeAdminApi(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id,
                    phone_confirmed_at="2026-01-01T00:00:00Z",
                    identities=[],
                )
            }
        )
        client = FakeClient(admin)

        outcomes = ensure_auth_personas(client, personas=(CUSTOMER,))

        assert outcomes == {"CUSTOMER_A": "recreated-legacy-row"}
        delete_index = admin.calls.index(("delete", CUSTOMER.user_id))
        create_index = admin.calls.index(("create", CUSTOMER.user_id))
        assert delete_index < create_index
        user = admin.users[CUSTOMER.user_id]
        assert any(identity.provider == "phone" for identity in user.identities)

    def test_reseed_is_idempotent(self) -> None:
        admin = FakeAdminApi()
        client = FakeClient(admin)

        first = ensure_auth_personas(client, personas=(CUSTOMER, VENDOR))
        calls_after_first = list(admin.calls)
        second = ensure_auth_personas(client, personas=(CUSTOMER, VENDOR))

        assert first == {"CUSTOMER_A": "created", "APPROVED_VENDOR_A": "created"}
        assert second == {"CUSTOMER_A": "already-ok", "APPROVED_VENDOR_A": "already-ok"}
        # Second pass only ever GETs — never re-creates, deletes, or updates.
        new_calls = admin.calls[len(calls_after_first) :]
        assert all(method == "get" for method, _ in new_calls)

    def test_preserves_deterministic_uuids_across_create_and_recreate(self) -> None:
        admin = FakeAdminApi(
            seed_users={
                VENDOR.user_id: _User(
                    id=VENDOR.user_id, phone_confirmed_at="2026-01-01T00:00:00Z", identities=[]
                )
            }
        )
        client = FakeClient(admin)

        ensure_auth_personas(client, personas=(CUSTOMER, VENDOR))

        assert admin.users[CUSTOMER.user_id].id == CUSTOMER.user_id
        assert admin.users[VENDOR.user_id].id == VENDOR.user_id

    def test_touches_only_canonical_synthetic_ids(self) -> None:
        """Never a dynamically discovered id — only the fixed ids passed in
        `personas` are ever looked up, created, deleted, or updated."""
        admin = FakeAdminApi(
            seed_users={
                UNRELATED_REAL_USER_ID: _User(
                    id=UNRELATED_REAL_USER_ID,
                    phone_confirmed_at="2020-01-01T00:00:00Z",
                    identities=[_Identity("phone", UNRELATED_REAL_USER_ID)],
                )
            }
        )
        client = FakeClient(admin)

        ensure_auth_personas(client, personas=(CUSTOMER, VENDOR))

        touched_ids = {uid for _, uid in admin.calls}
        assert touched_ids == {CUSTOMER.user_id, VENDOR.user_id}
        assert UNRELATED_REAL_USER_ID not in touched_ids
        # The unrelated real user's row is completely untouched.
        assert admin.users[UNRELATED_REAL_USER_ID].phone_confirmed_at == "2020-01-01T00:00:00Z"

    def test_fails_closed_on_create_error(self) -> None:
        class _BoomAdmin(FakeAdminApi):
            def create_user(self, attributes: dict[str, Any]) -> Any:
                raise RuntimeError("network timeout")

        admin = _BoomAdmin()
        client = FakeClient(admin)

        with pytest.raises(AuthPersonaError):
            ensure_auth_personas(client, personas=(CUSTOMER,))

    def test_fails_closed_on_lookup_error_other_than_not_found(self) -> None:
        class _BoomAdmin(FakeAdminApi):
            def get_user_by_id(self, uid: str) -> Any:
                raise _AdminApiError(status=500)

        admin = _BoomAdmin()
        client = FakeClient(admin)

        with pytest.raises(AuthPersonaError):
            ensure_auth_personas(client, personas=(CUSTOMER,))

    def test_fails_closed_on_delete_error_during_recreation(self) -> None:
        class _BoomAdmin(FakeAdminApi):
            def delete_user(self, uid: str, should_soft_delete: bool = False) -> None:
                raise RuntimeError("delete refused")

        admin = _BoomAdmin(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id, phone_confirmed_at="2026-01-01T00:00:00Z", identities=[]
                )
            }
        )
        client = FakeClient(admin)

        with pytest.raises(AuthPersonaError):
            ensure_auth_personas(client, personas=(CUSTOMER,))


class TestVerifyAuthPersonas:
    def test_passes_when_contract_met(self) -> None:
        admin = FakeAdminApi(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id,
                    phone_confirmed_at="2026-01-01T00:00:00Z",
                    identities=[_Identity("phone", CUSTOMER.user_id)],
                )
            }
        )
        client = FakeClient(admin)

        verify_auth_personas(client, personas=(CUSTOMER,))  # must not raise

    def test_fails_closed_when_user_missing(self) -> None:
        admin = FakeAdminApi()
        client = FakeClient(admin)

        with pytest.raises(AuthPersonaError, match="does not exist"):
            verify_auth_personas(client, personas=(CUSTOMER,))

    def test_fails_closed_when_phone_not_confirmed(self) -> None:
        admin = FakeAdminApi(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id,
                    phone_confirmed_at=None,
                    identities=[_Identity("phone", CUSTOMER.user_id)],
                )
            }
        )
        client = FakeClient(admin)

        with pytest.raises(AuthPersonaError, match="phone_confirmed_at"):
            verify_auth_personas(client, personas=(CUSTOMER,))

    def test_fails_closed_when_no_phone_identity(self) -> None:
        admin = FakeAdminApi(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id, phone_confirmed_at="2026-01-01T00:00:00Z", identities=[]
                )
            }
        )
        client = FakeClient(admin)

        with pytest.raises(AuthPersonaError, match="provider='phone'"):
            verify_auth_personas(client, personas=(CUSTOMER,))

    def test_fails_closed_when_phone_identity_owned_by_a_different_user(self) -> None:
        """A phone identity existing somewhere is not enough — it must be
        owned by this exact persona's user id."""
        admin = FakeAdminApi(
            seed_users={
                CUSTOMER.user_id: _User(
                    id=CUSTOMER.user_id,
                    phone_confirmed_at="2026-01-01T00:00:00Z",
                    identities=[_Identity("phone", "some-other-user-id")],
                )
            }
        )
        client = FakeClient(admin)

        with pytest.raises(AuthPersonaError, match="provider='phone'"):
            verify_auth_personas(client, personas=(CUSTOMER,))
