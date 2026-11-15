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
SESSION_A = "b9a00000-0000-4000-8000-00000000000a"


def _seed_listing(db: PgConn) -> None:
    cleaned = db.run(
        f"DELETE FROM public.listing_view_dedup WHERE listing_id = '{LISTING_A}'; "
        f"DELETE FROM public.listing_analytics WHERE listing_id = '{LISTING_A}';"
    )
    assert cleaned.ok, cleaned.error
    script = (
        "BEGIN;\n"
        "SET LOCAL role service_role;\n"
        'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'
        f"""
INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
VALUES ('{VENDOR_A}', '{OWNER_A}', 'views-test-vendor', 'Views Test Vendor', 'active', 1)
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.vendor_listings (
  id, vendor_id, product_id, title_override, price_ngwee, condition, stock_mode, status
) VALUES (
  '{LISTING_A}', '{VENDOR_A}', 'b0000000-0000-0000-0000-000000000001',
  'Views Test Listing', 10000, 'new', 'always_available', 'active'
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


def test_impression_deduped_per_session_listing_day(db_url_env: None, db: PgConn) -> None:
    db.run(f"DELETE FROM public.listing_view_dedup WHERE session_id = '{SESSION_A}';")
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


# --- analytics_v2 surface attribution + vendor self-view exclusion (1A-06) ---------


def test_db_surface_is_recorded_and_vendor_self_view_excluded(db_url_env: None, db: PgConn) -> None:
    session = str(uuid.uuid4())
    counted = record_listing_views(
        session_id=session,
        listing_ids=[LISTING_A],
        view_kind="impression",
        surface="plp",
    )
    assert counted == 1
    row = db.run(
        "SELECT surface FROM public.listing_view_dedup "
        f"WHERE session_id = '{session}' AND listing_id = '{LISTING_A}';"
    )
    assert row.ok and [r.strip() for r in row.rows] == ["plp"]

    owner_view = record_listing_views(
        session_id=str(uuid.uuid4()),
        listing_ids=[LISTING_A],
        view_kind="pdp_view",
        surface="pdp",
        viewer_user_id=OWNER_A,
    )
    assert owner_view == 0
    shopper_view = record_listing_views(
        session_id=str(uuid.uuid4()),
        listing_ids=[LISTING_A],
        view_kind="pdp_view",
        surface="pdp",
        viewer_user_id=str(uuid.uuid4()),
    )
    assert shopper_view == 1


def test_db_invalid_surface_is_stored_as_unknown(db_url_env: None, db: PgConn) -> None:
    session = str(uuid.uuid4())
    assert (
        record_listing_views(
            session_id=session,
            listing_ids=[LISTING_A],
            view_kind="impression",
            surface="banner<script>",
        )
        == 1
    )
    row = db.run(f"SELECT surface FROM public.listing_view_dedup WHERE session_id = '{session}';")
    assert row.ok and [r.strip() for r in row.rows] == ["unknown"]


class _Captured:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> int:
        self.calls.append(kwargs)
        return 1


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Generator[_Captured, None, None]:
    from app.routers import telemetry_views
    from app.services.analytics import flags

    cap = _Captured()
    monkeypatch.setattr(telemetry_views, "record_listing_views", cap)
    monkeypatch.setattr(telemetry_views, "bump_rate_counter", lambda **_: (True, 0))
    flags.clear_cache()
    yield cap
    flags.clear_cache()


def test_flag_off_ignores_surface_and_bearer(client: TestClient, captured: _Captured) -> None:
    from app.services.analytics import flags

    flags.override_for_tests(flags.COLLECT_FLAG, False)
    session = str(uuid.uuid4())
    response = client.post(
        "/telemetry/views",
        json={"session_id": session, "listing_id": LISTING_A, "surface": "pdp"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 200
    # Exactly the v1 call: no surface, no viewer.
    assert captured.calls == [
        {"session_id": session, "listing_ids": [LISTING_A], "view_kind": "pdp_view"}
    ]


def test_flag_on_passes_surface_for_impressions(client: TestClient, captured: _Captured) -> None:
    from app.services.analytics import flags

    flags.override_for_tests(flags.COLLECT_FLAG, True)
    session = str(uuid.uuid4())
    response = client.post(
        "/telemetry/views",
        json={"session_id": session, "listing_ids": [LISTING_A], "surface": "home"},
        headers={"Authorization": "Bearer ignored-for-impressions"},
    )
    assert response.status_code == 200
    assert captured.calls == [
        {
            "session_id": session,
            "listing_ids": [LISTING_A],
            "view_kind": "impression",
            "surface": "home",
            "viewer_user_id": None,
        }
    ]


def test_flag_on_resolves_viewer_for_pdp_views(
    client: TestClient, captured: _Captured, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routers import telemetry_views
    from app.services.analytics import flags

    flags.override_for_tests(flags.COLLECT_FLAG, True)
    monkeypatch.setattr(telemetry_views, "verify_supabase_jwt", lambda token, _s: {"sub": OWNER_A})
    session = str(uuid.uuid4())
    response = client.post(
        "/telemetry/views",
        json={"session_id": session, "listing_id": LISTING_A, "surface": "pdp"},
        headers={"Authorization": "Bearer owner-token"},
    )
    assert response.status_code == 200
    assert captured.calls[0]["viewer_user_id"] == OWNER_A
    assert captured.calls[0]["surface"] == "pdp"


def test_flag_on_invalid_token_counts_as_anonymous(
    client: TestClient, captured: _Captured, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routers import telemetry_views
    from app.services.analytics import flags

    flags.override_for_tests(flags.COLLECT_FLAG, True)

    def _boom(token: str, _s: object) -> dict[str, object]:
        raise ValueError("bad token")

    monkeypatch.setattr(telemetry_views, "verify_supabase_jwt", _boom)
    response = client.post(
        "/telemetry/views",
        json={"session_id": str(uuid.uuid4()), "listing_id": LISTING_A},
        headers={"Authorization": "Bearer garbage"},
    )
    assert response.status_code == 200
    assert captured.calls[0]["viewer_user_id"] is None
    assert captured.calls[0]["surface"] == "unknown"


def test_normalize_surface() -> None:
    from app.services.analytics.listing_views import normalize_surface

    assert normalize_surface("plp") == "plp"
    assert normalize_surface(None) == "unknown"
    assert normalize_surface("PLP") == "unknown"
    assert normalize_surface("anything") == "unknown"
