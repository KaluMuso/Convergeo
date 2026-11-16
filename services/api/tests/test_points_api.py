"""Points + vendor-digest endpoints: authz, flag gate, response shape, template render."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.db import SqlResult
from app.services.notifications.templates.whatsapp import render_whatsapp_template
from app.services.points.redeem import RedeemUnavailable, redeem_points_for_coupon
from fastapi.testclient import TestClient

TOKEN = "test-points-token"
USER = "11111111-1111-1111-1111-111111111111"


class _Q:
    def __init__(self, rows: list[dict[str, Any]], calls: list[tuple[str, Any]]) -> None:
        self._rows, self._calls = rows, calls

    def __getattr__(self, name: str) -> Any:
        def chain(*args: Any, **kwargs: Any) -> _Q:
            self._calls.append((name, args))
            return self

        return chain

    def execute(self) -> MagicMock:
        return MagicMock(data=self._rows)


class _Fake:
    def __init__(self, *, flag: bool) -> None:
        self.flag = flag
        self.calls: list[tuple[str, Any]] = []

    def table(self, name: str) -> _Q:
        rows: list[dict[str, Any]] = []
        if name == "feature_flags":
            rows = [{"enabled": self.flag}]
        elif name == "platform_config":
            rows = [{"value": 500}]
        elif name == "points_ledger":
            rows = [
                {
                    "id": "e1",
                    "points": 120,
                    "reason": "order_completed",
                    "order_id": "o1",
                    "created_at": "2026-11-16T08:00:00+00:00",
                },
            ]
        return _Q(rows, self.calls)

    def rpc(self, name: str, params: dict[str, Any]) -> _Q:
        self.calls.append(("rpc", (name, params)))
        return _Q({"balance": 460, "lifetime_earned": 460}, self.calls)  # type: ignore[arg-type]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("INTERNAL_DIGEST_TOKEN", TOKEN)
    monkeypatch.setattr("app.routers.points.bump_rate_counter", lambda **_: (True, 0))
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.app_ref = app  # type: ignore[attr-defined]
        yield c


def _login(c: TestClient, fake: _Fake) -> None:
    app = c.app_ref  # type: ignore[attr-defined]
    wrapper = MagicMock()
    wrapper.client = fake
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=USER, roles=frozenset({"customer"}), token="t"
    )
    app.dependency_overrides[get_supabase_client] = lambda: wrapper


def test_me_points_requires_auth(client: TestClient) -> None:
    assert client.get("/me/points").status_code == 401


def test_me_points_flag_off_is_404(client: TestClient) -> None:
    _login(client, _Fake(flag=False))
    assert client.get("/me/points").status_code == 404


def test_me_points_own_rows_only(client: TestClient) -> None:
    fake = _Fake(flag=True)
    _login(client, fake)
    resp = client.get("/me/points")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balance"] == 460
    assert body["points_to_next"] == 40
    assert body["redeem_available"] is False
    assert ("eq", ("user_id", USER)) in fake.calls
    assert ("rpc", ("points_summary", {"p_user": USER})) in fake.calls


@pytest.mark.parametrize("path", ["/internal/points/sweep", "/internal/vendor-digest/weekly"])
def test_internal_endpoints_need_token(client: TestClient, path: str) -> None:
    assert client.post(path).status_code == 401
    assert client.post(path, headers={"X-Internal-Token": "wrong"}).status_code == 401


def test_vendor_digest_flag_off_sends_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts: list[str] = []

    def run(script: str) -> SqlResult:
        scripts.append(script)
        return SqlResult(ok=True, rows=["false"])

    monkeypatch.setattr("app.routers.internal_vendor_digest.run_sql_script", run)
    resp = client.post("/internal/vendor-digest/weekly", headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "sent": False, "vendors": []}
    assert not any("vendor_weekly_digest(" in s for s in scripts)


def test_points_sweep_with_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.points.ledger.run_sql_script",
        lambda _s: SqlResult(ok=True, rows=['{"enabled": false, "awarded": 0}']),
    )
    resp = client.post("/internal/points/sweep", headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_whatsapp_templates_render() -> None:
    pts = render_whatsapp_template(
        "points_earned", {"to": "+260971234567", "points": 120, "balance": 460, "threshold": 500}
    )
    assert pts.body_parameters == ("120", "460", "500")
    digest = render_whatsapp_template(
        "vendor_weekly_digest",
        {
            "to": "+260971234567",
            "shop_name": "Shop",
            "orders": 12,
            "sales_ngwee": 348_000,
            "top_item": None,
            "new_followers": 4,
            "pending_actions": 1,
            "next_payout_ngwee": 290_000,
        },
    )
    assert digest.body_parameters == ("Shop", "12", "K3,480.00", "-", "4", "1", "K2,900.00")


def test_redeem_is_a_todo_seam() -> None:
    with pytest.raises(RedeemUnavailable):
        redeem_points_for_coupon(user_id=USER, points=500, idempotency_key="k")
