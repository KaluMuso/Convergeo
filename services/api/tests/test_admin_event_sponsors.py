"""Admin review of event sponsors: authz, queue, decision, audit, stale-name 409."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient
from tests.test_vendor_plans import FakeDb, FakeService

ADMIN_ID = "00000000-0000-0000-0000-0000000a0001"
EVENT_ID = "eeeeeeee-0000-0000-0000-000000000001"
AUTH = {"Authorization": "Bearer t"}


class Harness:
    def __init__(self, db: FakeDb, client: TestClient) -> None:
        self.db = db
        self.client = client
        self.user = CurrentUser(id=ADMIN_ID, roles=frozenset({"admin"}), token="t")


def _seed(db: FakeDb) -> None:
    db.rows("events").append(
        {
            "id": EVENT_ID,
            "title": "Gospel Night",
            "slug": "gospel-night",
            "status": "published",
            "sponsor_review_pending": True,
            "archetype_details": {
                "stages": ["Main"],
                "sponsors": [
                    {"name": "Mosi", "logo": "sponsors/mosi", "status": "approved"},
                    {"name": "Zam", "link_url": "https://zam.example", "status": "pending"},
                ],
            },
            "vendors": {"display_name": "Grace Events"},
        }
    )


@pytest.fixture
def h(monkeypatch: pytest.MonkeyPatch) -> Generator[Harness, None, None]:
    app = create_app()
    holder: dict[str, Harness] = {}

    async def current_user() -> CurrentUser:
        return holder["h"].user

    def service_dep() -> Generator[FakeService, None, None]:
        yield FakeService(holder["h"].db)

    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    monkeypatch.setattr(
        "app.core.auth.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_supabase_client] = service_dep
    with TestClient(app, raise_server_exceptions=False) as client:
        db = FakeDb()
        _seed(db)
        holder["h"] = Harness(db, client)
        yield holder["h"]
    app.dependency_overrides.clear()


def _review(h: Harness, **overrides: Any) -> Any:
    body: dict[str, Any] = {"index": 1, "name": "Zam", "decision": "approved"}
    body.update(overrides)
    return h.client.post(f"/admin/event-sponsors/{EVENT_ID}/review", json=body, headers=AUTH)


def test_non_admin_cannot_reach_queue_or_review(h: Harness) -> None:
    h.user = CurrentUser(id="u1", roles=frozenset({"vendor"}), token="t")
    assert h.client.get("/admin/event-sponsors", headers=AUTH).status_code == 403
    assert _review(h).status_code == 403
    assert h.db.rows("audit_log") == []


def test_queue_lists_only_pending_sponsors(h: Harness) -> None:
    response = h.client.get("/admin/event-sponsors", headers=AUTH)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Gospel Night"
    assert items[0]["organiser_name"] == "Grace Events"
    assert [(s["index"], s["name"]) for s in items[0]["sponsors"]] == [(1, "Zam")]


def test_approve_updates_status_clears_flag_and_audits_once(h: Harness) -> None:
    response = _review(h, note="logo ok")
    assert response.status_code == 200, response.text
    assert response.json()["pending_remaining"] is False
    event = h.db.rows("events")[0]
    assert event["archetype_details"]["sponsors"][1]["status"] == "approved"
    assert event["archetype_details"]["stages"] == ["Main"]
    assert event["sponsor_review_pending"] is False
    audits = h.db.rows("audit_log")
    assert len(audits) == 1 and audits[0]["action"] == "event_sponsors.approved"


def test_reject_keeps_sponsor_hidden(h: Harness) -> None:
    assert _review(h, decision="rejected", note="logo unclear").status_code == 200
    event = h.db.rows("events")[0]
    assert event["archetype_details"]["sponsors"][1]["status"] == "rejected"
    assert event["sponsor_review_pending"] is False
    assert h.db.rows("audit_log")[0]["action"] == "event_sponsors.rejected"


def test_stale_name_is_409_and_writes_nothing(h: Harness) -> None:
    response = _review(h, name="Someone Else")
    assert response.status_code == 409
    assert h.db.rows("audit_log") == []
    assert h.db.rows("events")[0]["archetype_details"]["sponsors"][1]["status"] == "pending"


def test_unknown_event_and_bad_index_are_404(h: Harness) -> None:
    missing = h.client.post(
        "/admin/event-sponsors/eeeeeeee-0000-0000-0000-0000000000ff/review",
        json={"index": 0, "name": "Mosi", "decision": "approved"},
        headers=AUTH,
    )
    assert missing.status_code == 404
    assert _review(h, index=5).status_code == 404


def test_rejects_invalid_decision(h: Harness) -> None:
    assert _review(h, decision="pending").status_code == 422
