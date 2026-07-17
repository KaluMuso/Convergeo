"""Organiser attendee roster (Events Wave B) — ownership guard, JSON-row parsing
(an attendee name may contain ``|``), counts, and input validation.

Isolation-clean: ``run_sql_script`` is mocked (dispatched on script content), so no
Postgres is needed — this runs under the plain ``python`` CI job.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.orders.audit import SqlResult
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EVENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
INSTANCE_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"

_OWNER_VENDOR = {USER_A_ID: VENDOR_A_ID, USER_B_ID: VENDOR_B_ID}


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    app = create_app()
    service_wrapper = MagicMock()
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper

    with patch(
        "app.core.auth.verify_supabase_jwt",
        side_effect=lambda token, settings: {
            TOKEN_A: {"sub": USER_A_ID, "exp": 9_999_999_999},
            TOKEN_B: {"sub": USER_B_ID, "exp": 9_999_999_999},
        }[token],
    ), patch(
        "app.core.auth._load_user_roles",
        side_effect=lambda user_id, service_client: frozenset({"vendor"}),
    ), patch(
        "app.deps.get_supabase_service_client",
        return_value=service_wrapper,
    ), patch(
        "app.supabase_client.get_supabase_service_client",
        return_value=service_wrapper,
    ):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()


def _dispatch(
    *,
    event_owner: str | None,
    counts: tuple[int, int] = (0, 0),
    attendee_rows: list[dict[str, Any]] | None = None,
) -> Callable[[str], SqlResult]:
    rows = attendee_rows or []

    def _run(script: str) -> SqlResult:
        if "FROM public.vendors" in script:
            for user_id, vendor_id in _OWNER_VENDOR.items():
                if user_id in script:
                    return SqlResult(ok=True, rows=[vendor_id])
            return SqlResult(ok=True, rows=[])
        if "FROM public.events" in script:
            if event_owner is None:
                return SqlResult(ok=True, rows=[])
            return SqlResult(ok=True, rows=[f"{event_owner}|published"])
        if "count(*) FILTER" in script:
            return SqlResult(ok=True, rows=[f"{counts[0]}|{counts[1]}"])
        if "json_build_object" in script:
            return SqlResult(ok=True, rows=[json.dumps(row) for row in rows])
        return SqlResult(ok=True, rows=[])

    return _run


def _attendee(**overrides: Any) -> dict[str, Any]:
    base = {
        "ticket_id": "11111111-1111-1111-1111-111111111aaa",
        "holder_name": "Chanda Mumba",
        "ticket_type_id": "22222222-2222-2222-2222-2222222222bb",
        "ticket_type_name": "VIP",
        "kind": "fixed",
        "instance_id": INSTANCE_ID,
        "starts_at": "2026-08-01T18:00:00+00:00",
        "status": "issued",
        "checked_in_at": None,
    }
    base.update(overrides)
    return base


def test_roster_returns_attendees_and_counts(api_client: TestClient) -> None:
    rows = [
        _attendee(status="checked_in", checked_in_at="2026-08-01T18:05:00+00:00"),
        # A name containing "|" must survive — proves the json_build_object row
        # format is immune to psql's pipe field separator.
        _attendee(
            ticket_id="11111111-1111-1111-1111-111111111ccc",
            holder_name="Banda | Phiri",
        ),
        _attendee(
            ticket_id="11111111-1111-1111-1111-111111111ddd",
            holder_name=None,
        ),
    ]
    with patch(
        "app.routers.organiser_stats.run_sql_script",
        side_effect=_dispatch(event_owner=VENDOR_A_ID, counts=(3, 1), attendee_rows=rows),
    ):
        response = api_client.get(
            f"/organiser/events/{EVENT_ID}/roster",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["checked_in"] == 1
    assert body["truncated"] is False
    assert len(body["attendees"]) == 3
    names = [a["holder_name"] for a in body["attendees"]]
    assert "Banda | Phiri" in names
    assert None in names
    assert body["attendees"][0]["status"] == "checked_in"


def test_roster_cross_vendor_forbidden(api_client: TestClient) -> None:
    with patch(
        "app.routers.organiser_stats.run_sql_script",
        side_effect=_dispatch(event_owner=VENDOR_A_ID),
    ):
        response = api_client.get(
            f"/organiser/events/{EVENT_ID}/roster",
            headers={"Authorization": f"Bearer {TOKEN_B}"},
        )
    assert response.status_code == 403


def test_roster_missing_event_404(api_client: TestClient) -> None:
    with patch(
        "app.routers.organiser_stats.run_sql_script",
        side_effect=_dispatch(event_owner=None),
    ):
        response = api_client.get(
            f"/organiser/events/{EVENT_ID}/roster",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
    assert response.status_code == 404


def test_roster_bad_instance_id_422(api_client: TestClient) -> None:
    # Validated before any SQL runs.
    response = api_client.get(
        f"/organiser/events/{EVENT_ID}/roster?instance_id=not-a-uuid",
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    assert response.status_code == 422


def test_roster_requires_auth(api_client: TestClient) -> None:
    response = api_client.get(f"/organiser/events/{EVENT_ID}/roster")
    assert response.status_code == 401
