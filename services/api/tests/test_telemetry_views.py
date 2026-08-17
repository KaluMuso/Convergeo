"""Telemetry listing views — impressions and PDP views."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from app.services.analytics.listing_views import clear_dedup_store_cache, record_listing_views
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

LISTING_A = "b9100000-0000-0000-0000-00000000000a"
VENDOR_A = "b9a00000-0000-0000-0000-00000000000a"
OWNER_A = "33333333-3333-3333-3333-333333333333"
SESSION_A = "b9s00000-0000-0000-0000-00000000000a"


def _seed_listing(db: PgConn) -> None:
    script = (
        "BEGIN;\n"
        "SET LOCAL role service_role;\n"
        'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'
        f"""
DELETE FROM public.listing_view_dedup WHERE listing_id = '{LISTING_A}';
DELETE FROM public.listing_analytics WHERE listing_id = '{LISTING_A}';
INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
VALUES ('{VENDOR_A}', '{OWNER_A}', 'views-test-vendor', 'Views Test Vendor', 'active', 1)
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.vendor_listings (
  id, vendor_id, title_override, price_ngwee, condition, stock_mode, status
) VALUES (
  '{LISTING_A}', '{VENDOR_A}', 'Views Test Listing', 10000, 'new', 'always_available', 'active'
)
ON CONFLICT (id) DO NOTHING;
"""
        "COMMIT;\n"
    )
    result = db.run(script)
    assert result.ok, result.error


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    _seed_listing(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    clear_dedup_store_cache()
    yield
    clear_dedup_store_cache()
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def test_impression_deduped_per_session_listing_day(db_url_env: None) -> None:
    first = record_listing_views(
        session_id=SESSION_A,
        listing_ids=[LISTING_A],
        view_kind="impression",
    )
    second = record_listing_views(
        session_id=SESSION_A,
        listing_ids=[LISTING_A],
        view_kind="impression",
    )
    assert first == 1
    assert second == 0


def test_pdp_view_deduped_separately_from_impression(db_url_env: None) -> None:
    session = str(uuid.uuid4())
    imp = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A],
        view_kind="impression",
    )
    pdp = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A],
        view_kind="pdp_view",
    )
    assert imp == 1
    assert pdp == 1


def test_impression_batch_counts_unique_listings(db_url_env: None) -> None:
    session = str(uuid.uuid4())
    counted = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A, LISTING_A],
        view_kind="impression",
    )
    assert counted == 1


def test_telemetry_views_endpoint_accepts_impressions(client: TestClient) -> None:
    session = str(uuid.uuid4())
    response = client.post(
        "/telemetry/views",
        json={"session_id": session, "listing_ids": [LISTING_A]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == 1
    assert body["queued"] is True


def test_telemetry_views_endpoint_accepts_pdp_view(client: TestClient) -> None:
    session = str(uuid.uuid4())
    response = client.post(
        "/telemetry/views",
        json={"session_id": session, "listing_id": LISTING_A},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1


def test_telemetry_views_rejects_missing_session(client: TestClient) -> None:
    response = client.post(
        "/telemetry/views",
        json={"listing_id": LISTING_A},
    )
    assert response.status_code == 422


def test_telemetry_views_rejects_both_shapes(client: TestClient) -> None:
    response = client.post(
        "/telemetry/views",
        json={
            "session_id": str(uuid.uuid4()),
            "listing_id": LISTING_A,
            "listing_ids": [LISTING_A],
        },
    )
    assert response.status_code == 422


def test_telemetry_views_defaults_surface_to_unknown(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    captured: dict[str, object] = {}

    def _fake(**kwargs: object) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr("app.routers.telemetry_views.record_listing_views", _fake)
    session = str(uuid.uuid4())
    response = client.post(
        "/telemetry/views",
        json={"session_id": session, "listing_ids": [LISTING_A]},
    )
    assert response.status_code == 200
    assert captured["surface"] == "unknown"
    assert captured["viewer_user_id"] is None
    assert captured["view_kind"] == "impression"


def test_telemetry_views_accepts_explicit_surface(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    captured: dict[str, object] = {}

    def _fake(**kwargs: object) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr("app.routers.telemetry_views.record_listing_views", _fake)
    session = str(uuid.uuid4())
    response = client.post(
        "/telemetry/views",
        json={"session_id": session, "listing_id": LISTING_A, "surface": "pdp"},
    )
    assert response.status_code == 200
    assert captured["surface"] == "pdp"
    assert captured["view_kind"] == "pdp_view"


def test_telemetry_views_rejects_invalid_surface(client: TestClient) -> None:
    response = client.post(
        "/telemetry/views",
        json={
            "session_id": str(uuid.uuid4()),
            "listing_id": LISTING_A,
            "surface": "email",
        },
    )
    assert response.status_code == 422


def test_telemetry_views_rejects_viewer_id_in_body(client: TestClient) -> None:
    response = client.post(
        "/telemetry/views",
        json={
            "session_id": str(uuid.uuid4()),
            "listing_id": LISTING_A,
            "viewer_user_id": OWNER_A,
        },
    )
    assert response.status_code == 422


def test_telemetry_views_filters_obvious_bots(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    called = {"persist": False}

    def _fake(**_kwargs: object) -> int:
        called["persist"] = True
        return 1

    monkeypatch.setattr("app.routers.telemetry_views.record_listing_views", _fake)
    response = client.post(
        "/telemetry/views",
        json={"session_id": str(uuid.uuid4()), "listing_id": LISTING_A},
        headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": 0, "queued": False}
    assert called["persist"] is False


def test_telemetry_views_does_not_treat_whatsapp_as_bot(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    captured: dict[str, object] = {}

    def _fake(**kwargs: object) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr("app.routers.telemetry_views.record_listing_views", _fake)
    response = client.post(
        "/telemetry/views",
        json={"session_id": str(uuid.uuid4()), "listing_ids": [LISTING_A], "surface": "plp"},
        headers={"User-Agent": "WhatsApp/10.0.0 Android"},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    assert captured["surface"] == "plp"


def test_telemetry_views_forwards_bearer_viewer_without_storing_in_body(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    from app.core.auth import CurrentUser

    captured: dict[str, object] = {}

    def _fake(**kwargs: object) -> int:
        captured.update(kwargs)
        return 1

    async def _user(_request: object, _settings: object) -> CurrentUser:
        return CurrentUser(id=OWNER_A, roles=frozenset({"vendor"}), token="test-token")

    monkeypatch.setattr("app.routers.telemetry_views.record_listing_views", _fake)
    monkeypatch.setattr("app.routers.telemetry_views.get_current_user", _user)
    response = client.post(
        "/telemetry/views",
        json={"session_id": str(uuid.uuid4()), "listing_id": LISTING_A, "surface": "pdp"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert captured["viewer_user_id"] == OWNER_A
    assert "viewer_user_id" not in response.json()


def test_distinct_surfaces_are_not_collapsed(db_url_env: None) -> None:
    session = str(uuid.uuid4())
    home = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A],
        view_kind="impression",
        surface="home",
    )
    plp = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A],
        view_kind="impression",
        surface="plp",
    )
    assert home == 1
    assert plp == 1


def test_vendor_self_view_is_suppressed(db_url_env: None) -> None:
    session = str(uuid.uuid4())
    counted = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A],
        view_kind="pdp_view",
        surface="pdp",
        viewer_user_id=OWNER_A,
    )
    assert counted == 0


def test_non_owner_viewer_still_counts(db_url_env: None) -> None:
    session = str(uuid.uuid4())
    counted = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A],
        view_kind="pdp_view",
        surface="pdp",
        viewer_user_id="44444444-4444-4444-4444-444444444444",
    )
    assert counted == 1
