"""M18-P06 — admin review and publication control for WhatsApp intake.

The claims under test are the ones that make this a *gate* rather than a
formality:

* a non-admin cannot reach any of it;
* **no bulk-approve endpoint exists** — asserted against the live route table,
  not by reading the source, so nobody can add one without this failing;
* two reviewers approving at once produce one winner and one 409;
* re-running a completed action is a no-op, not a second write;
* a rejected intake leaves nothing publishable behind;
* approval re-checks the gates instead of trusting submission-time state;
* the vendor is notified through the Lane 1 outbox — never the WAHA lane.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.intake import state_machine
from fastapi.testclient import TestClient

ADMIN_USER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_USER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SESSION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING_ID = "99999999-9999-9999-9999-999999999999"
PRODUCT_ID = "77777777-7777-7777-7777-777777777777"
VALID_TOKEN = "valid.jwt.token"


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def is_(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("is", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in value:
                return False
            if op == "is" and value == "null" and row.get(column) is not None:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", f"row-{len(self._parent.rows)}-{self._parent.name}")
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._op == "update":
            assert self._payload is not None
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = [dict(row) for row in self._parent.rows if self._match(row)]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeBucket:
    def create_signed_url(self, path: str, ttl: int) -> dict[str, str]:
        return {"signedURL": f"https://signed.example/{path}?ttl={ttl}"}


class FakeStorage:
    def from_(self, name: str) -> FakeBucket:
        return FakeBucket()


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))


# --- Fixtures ---------------------------------------------------------------
@pytest.fixture
def app() -> Any:
    return create_app()


@pytest.fixture
def client(app: Any) -> Generator[TestClient, None, None]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    supabase = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = supabase
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.admin_intake.get_supabase_client", lambda: wrapper)

    # AdminAuditedRoute / recorder writes go to the same fake so audit rows are
    # inspectable without a database.
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client", lambda: wrapper
    )
    return supabase


def _auth(monkeypatch: pytest.MonkeyPatch, *, roles: frozenset[str]) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": ADMIN_USER_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: roles,
    )


def _admin(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch, roles=frozenset({"admin"}))


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _seed(
    fake: FakeSupabaseClient,
    *,
    status: str = state_machine.PENDING_ADMIN_REVIEW,
    listing_status: str = "draft",
    vendor_status: str = "active",
    draft: dict[str, Any] | None = None,
    with_listing: bool = True,
) -> None:
    fake.table("vendors").rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": VENDOR_USER_ID,
            "status": vendor_status,
            "kyc_tier": 2,
            "display_name": "Acme Shop",
        }
    )
    fake.table("intake_sessions").rows.append(
        {
            "id": SESSION_ID,
            "vendor_id": VENDOR_ID,
            "status": status,
            "pending_requests": [],
            "listing_id": LISTING_ID if with_listing else None,
            "submitted_at": "2026-07-01T00:00:00+00:00",
            "admin_notes": None,
        }
    )
    fake.table("intake_draft_fields").rows.append(
        {
            "session_id": SESSION_ID,
            "title": "Samsung Fridge",
            "price_ngwee": 350_000,
            "condition": "new",
            "description": "Barely used",
            **(draft or {}),
        }
    )
    fake.table("intake_field_provenance").rows.append(
        {
            "session_id": SESSION_ID,
            "field_name": "title",
            "source": "model",
            "confidence": 0.7,
            "model_ref": "test-model",
        }
    )
    if with_listing:
        fake.table("vendor_listings").rows.append(
            {
                "id": LISTING_ID,
                "vendor_id": VENDOR_ID,
                "product_id": None,
                "title_override": "Samsung Fridge",
                "price_ngwee": 350_000,
                "condition": "new",
                "status": listing_status,
            }
        )
    fake.table("products").rows.append(
        {"id": PRODUCT_ID, "name": "Samsung Fridge RT38", "aliases": [], "status": "active"}
    )
    fake.table("notification_outbox")
    fake.table("audit_log")
    fake.table("intake_events")


# --- Structural guarantees --------------------------------------------------
def test_no_bulk_approve_endpoint_exists(app: Any) -> None:
    """The absence of a batch route is the guarantee — assert it, don't trust it."""
    paths = list(app.openapi()["paths"])
    intake_paths = [path for path in paths if path.startswith("/admin/intake")]
    assert intake_paths, "admin intake routes should be mounted"
    for path in intake_paths:
        lowered = path.lower()
        assert "bulk" not in lowered
        assert "batch" not in lowered
    # Every action route is scoped to exactly one session id.
    for path in intake_paths:
        if path.endswith(("/approve", "/reject", "/request-changes", "/attach-canonical")):
            assert "{session_id}" in path


def test_queue_requires_admin(client: TestClient, fake: FakeSupabaseClient) -> None:
    _seed(fake)
    assert client.get("/admin/intake").status_code == 401


def test_queue_rejects_non_admin(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch, roles=frozenset({"vendor"}))
    assert client.get("/admin/intake", headers=_headers()).status_code == 403


def test_approve_rejects_non_admin(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch, roles=frozenset({"vendor"}))
    response = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert response.status_code == 403
    # And nothing was published on the way to being refused.
    assert fake.table("vendor_listings").rows[0]["status"] == "draft"


# --- Queue + detail ---------------------------------------------------------
def test_queue_lists_pending_sessions(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)
    rows = client.get("/admin/intake", headers=_headers()).json()
    assert len(rows) == 1
    assert rows[0]["session_id"] == SESSION_ID
    assert rows[0]["vendor_display_name"] == "Acme Shop"
    assert rows[0]["vendor_kyc_tier"] == 2


def test_queue_excludes_terminal_sessions(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, status=state_machine.APPROVED)
    _admin(monkeypatch)
    assert client.get("/admin/intake", headers=_headers()).json() == []


def test_detail_shows_provenance_media_and_candidates(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    fake.table("intake_media").rows.append(
        {
            "id": "media-1",
            "session_id": SESSION_ID,
            "storage_path": f"intake/{VENDOR_ID}/{SESSION_ID}/hash",
            "mime_type": "image/jpeg",
            "width_px": 800,
            "height_px": 600,
        }
    )
    _admin(monkeypatch)

    body = client.get(f"/admin/intake/{SESSION_ID}", headers=_headers()).json()
    assert body["provenance"][0]["source"] == "model"
    assert body["media"][0]["signed_url"].startswith("https://signed.example/")
    assert body["media"][0]["ttl_seconds"] == 600
    # Trigram match against the seeded active canonical product.
    assert body["canonical_candidates"][0]["product_id"] == PRODUCT_ID
    assert [entry["field_name"] for entry in body["listing_diff"]] == [
        "title",
        "price_ngwee",
        "condition",
    ]


def test_detail_warns_on_inactive_vendor(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, vendor_status="suspended")
    _admin(monkeypatch)
    body = client.get(f"/admin/intake/{SESSION_ID}", headers=_headers()).json()
    assert "admin.intake.warnings.vendorNotActive" in body["warnings"]


def test_detail_warns_on_used_condition(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, draft={"condition": "used"})
    _admin(monkeypatch)
    body = client.get(f"/admin/intake/{SESSION_ID}", headers=_headers()).json()
    assert "admin.intake.warnings.usedCondition" in body["warnings"]


def test_detail_404s_for_unknown_session(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/admin/intake/{unknown}", headers=_headers()).status_code == 404


# --- Approve ----------------------------------------------------------------
def test_approve_activates_through_a_guarded_transition(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)

    response = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["session_status"] == state_machine.APPROVED
    assert body["listing_status"] == "active"
    assert fake.table("vendor_listings").rows[0]["status"] == "active"
    # Audited.
    actions = [row.get("action") for row in fake.table("audit_log").rows]
    assert "admin.intake.approve" in actions


def test_approve_is_idempotent(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)

    first = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    second = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())

    assert first.json()["changed"] is True
    assert second.status_code == 200
    assert second.json()["changed"] is False
    assert second.json()["session_status"] == state_machine.APPROVED


def test_concurrent_approve_has_one_winner(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two reviewers hitting approve at once: one wins, the other gets a 409.

    The race window is between reading the session and transitioning it, so the
    loser is modelled as a request whose *read* still says
    ``pending_admin_review`` while the row has already moved to ``approved``.
    The guarded transition — not the handler's own status check — is what has to
    catch this, which is exactly what the assertion pins.
    """
    _seed(fake)
    _admin(monkeypatch)

    first = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert first.status_code == 200
    assert fake.table("intake_sessions").rows[0]["status"] == state_machine.APPROVED

    stale = dict(fake.table("intake_sessions").rows[0])
    stale["status"] = state_machine.PENDING_ADMIN_REVIEW
    monkeypatch.setattr(
        "app.routers.admin_intake._load_session", lambda service_client, session_id: stale
    )

    second = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "intake_invalid_transition"
    # The winner's outcome is untouched: still exactly one approval, one active listing.
    assert fake.table("intake_sessions").rows[0]["status"] == state_machine.APPROVED
    assert fake.table("vendor_listings").rows[0]["status"] == "active"


def test_approve_refuses_suspended_vendor(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gates are re-checked at approval, not trusted from submission time."""
    _seed(fake, vendor_status="suspended")
    _admin(monkeypatch)

    response = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "vendor_not_active"
    assert fake.table("vendor_listings").rows[0]["status"] == "draft"


def test_approve_refuses_prohibited_title(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)
    monkeypatch.setattr(
        "app.routers.admin_intake.screen_listing",
        lambda **kwargs: MagicMock(allowed=False, reason="keyword", matched="banned"),
    )

    response = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert response.status_code == 422
    assert fake.table("vendor_listings").rows[0]["status"] == "draft"


def test_approve_without_a_listing_is_refused(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, with_listing=False)
    _admin(monkeypatch)
    response = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "intake_listing_missing"


def test_approve_notifies_on_the_lane_1_outbox(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vendor notification is the official outbox. WAHA is inbound-only."""
    _seed(fake)
    _admin(monkeypatch)
    client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())

    outbox = fake.table("notification_outbox").rows
    assert len(outbox) == 1
    assert outbox[0]["template"] == "intake_approved"
    assert outbox[0]["status"] == "pending"


def test_approve_refuses_a_session_not_in_review(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, status=state_machine.COLLECTING)
    _admin(monkeypatch)
    response = client.post(f"/admin/intake/{SESSION_ID}/approve", headers=_headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "intake_session_not_reviewable"


# --- Reject / request changes ----------------------------------------------
def test_reject_removes_the_draft_listing(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected intake must leave nothing the vendor could publish later."""
    _seed(fake)
    _admin(monkeypatch)

    response = client.post(
        f"/admin/intake/{SESSION_ID}/reject",
        headers=_headers(),
        json={"reason": "Counterfeit branding"},
    )
    assert response.status_code == 200
    assert response.json()["session_status"] == state_machine.REJECTED
    assert fake.table("vendor_listings").rows[0]["status"] == "removed"
    assert fake.table("intake_sessions").rows[0]["rejection_reason"] == "Counterfeit branding"


def test_reject_requires_a_reason(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)
    response = client.post(
        f"/admin/intake/{SESSION_ID}/reject", headers=_headers(), json={"reason": ""}
    )
    assert response.status_code == 422


def test_reject_is_idempotent(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)
    payload = {"reason": "Counterfeit branding"}
    client.post(f"/admin/intake/{SESSION_ID}/reject", headers=_headers(), json=payload)
    second = client.post(
        f"/admin/intake/{SESSION_ID}/reject", headers=_headers(), json=payload
    )
    assert second.status_code == 200
    assert second.json()["changed"] is False


def test_request_changes_sends_it_back(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)

    response = client.post(
        f"/admin/intake/{SESSION_ID}/request-changes",
        headers=_headers(),
        json={"reason": "Please add a clearer photo"},
    )
    assert response.status_code == 200
    assert response.json()["session_status"] == state_machine.NEEDS_DETAILS
    assert (
        fake.table("intake_sessions").rows[0]["admin_notes"] == "Please add a clearer photo"
    )
    # The listing stays a draft — a change request is not a rejection.
    assert fake.table("vendor_listings").rows[0]["status"] == "draft"


def test_request_changes_is_idempotent(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, status=state_machine.NEEDS_DETAILS)
    _admin(monkeypatch)
    response = client.post(
        f"/admin/intake/{SESSION_ID}/request-changes",
        headers=_headers(),
        json={"reason": "again"},
    )
    assert response.status_code == 200
    assert response.json()["changed"] is False


# --- Attach canonical -------------------------------------------------------
def test_attach_canonical_points_the_listing_at_the_product(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)

    response = client.post(
        f"/admin/intake/{SESSION_ID}/attach-canonical",
        headers=_headers(),
        json={"product_id": PRODUCT_ID},
    )
    assert response.status_code == 200
    assert fake.table("vendor_listings").rows[0]["product_id"] == PRODUCT_ID
    # Attaching is not approving.
    assert fake.table("vendor_listings").rows[0]["status"] == "draft"
    assert fake.table("intake_sessions").rows[0]["status"] == state_machine.PENDING_ADMIN_REVIEW


def test_attach_canonical_refuses_a_non_active_product(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attaching a pending canonical would publish it through the back door."""
    _seed(fake)
    fake.table("products").rows[0]["status"] = "pending_moderation"
    _admin(monkeypatch)

    response = client.post(
        f"/admin/intake/{SESSION_ID}/attach-canonical",
        headers=_headers(),
        json={"product_id": PRODUCT_ID},
    )
    assert response.status_code == 422
    assert fake.table("vendor_listings").rows[0]["product_id"] is None


def test_attach_canonical_is_idempotent(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)
    payload = {"product_id": PRODUCT_ID}
    client.post(
        f"/admin/intake/{SESSION_ID}/attach-canonical", headers=_headers(), json=payload
    )
    second = client.post(
        f"/admin/intake/{SESSION_ID}/attach-canonical", headers=_headers(), json=payload
    )
    assert second.status_code == 200
    assert second.json()["changed"] is False


def test_attach_canonical_404s_for_unknown_product(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _admin(monkeypatch)
    response = client.post(
        f"/admin/intake/{SESSION_ID}/attach-canonical",
        headers=_headers(),
        json={"product_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404
