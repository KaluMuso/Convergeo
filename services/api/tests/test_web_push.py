"""Web Push sender: payload (locale, no PII), transport, queue processing, fail-closed.

Keys are generated per test run (nothing key-like is committed); HTTP is mocked
with ``httpx.MockTransport`` — no real push service is ever contacted.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import http_ece  # type: ignore[import-untyped]
import httpx
import pytest
from app.services.notifications import web_push as wp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from scripts.sync_web_push_messages import build_snapshot, render
from tests.test_notifications_center import Store

USER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/fake-endpoint-for-tests"
NOW = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)  # 12:00 in Lusaka (outside quiet hours)


# --- helpers -----------------------------------------------------------------------------
def _receiver() -> tuple[ec.EllipticCurvePrivateKey, str, bytes, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    auth = os.urandom(16)
    return key, wp.urlsafe_b64(public), auth, wp.urlsafe_b64(auth)


def _vapid() -> wp.VapidConfig:
    key = ec.generate_private_key(ec.SECP256R1())
    raw = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return wp.VapidConfig(
        public_key=wp.urlsafe_b64(public),
        private_key=wp.urlsafe_b64(raw),
        subject="mailto:ops@example.test",
    )


def _notification(**extra: Any) -> dict[str, Any]:
    return {
        "id": "n-1",
        "recipient_user_id": USER,
        "audience": "customer",
        "i18n_key": "notifications.inApp.customer.order_ready_pickup",
        "params": {"ref": "AB12CD", "pickup_pin": "4321", "qr_token": "qr-secret"},
        "link_path": "/account/orders/abc-123",
        "created_at": (NOW - timedelta(minutes=5)).isoformat(),
        "seen_at": None,
        "read_at": None,
        **extra,
    }


def _store(*, flag: bool = True, locale: str = "bem", attempts: int = 0) -> Store:
    st = Store()
    st.table("feature_flags").rows.append({"flag": "web_push", "enabled": flag})
    st.table("profiles").rows.append({"id": USER, "locale": locale})
    st.table("in_app_notifications").rows.append(_notification())
    st.table("web_push_subscriptions").rows.append(
        {
            "id": "sub-1",
            "user_id": USER,
            "audience": "customer",
            "endpoint": ENDPOINT,
            "p256dh": "p" * 20,
            "auth_secret": "a" * 12,
        }
    )
    st.table("web_push_deliveries").rows.append(
        {
            "id": "d-1",
            "notification_id": "n-1",
            "subscription_id": "sub-1",
            "recipient_user_id": USER,
            "status": "pending",
            "attempts": attempts,
            "next_attempt_at": (NOW - timedelta(seconds=1)).isoformat(),
        }
    )
    return st


class Recorder:
    def __init__(self, *outcomes: wp.SendOutcome) -> None:
        self.outcomes = list(outcomes) or [wp.SendOutcome(status_code=201)]
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> wp.SendOutcome:
        self.calls.append(kwargs)
        return self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]


def _dispatcher(st: Store, send: Recorder, **kwargs: Any) -> wp.WebPushDispatcher:
    kwargs.setdefault("rate_limiter", lambda _user: True)
    return wp.WebPushDispatcher(st, send, **kwargs)


def _delivery(st: Store) -> dict[str, Any]:
    return st.table("web_push_deliveries").rows[0]


# --- catalog + payload ------------------------------------------------------------------
def test_message_snapshot_matches_the_i18n_catalog() -> None:
    assert wp._MESSAGES_PATH.read_text("utf-8") == render(build_snapshot()), (
        "run: uv run python scripts/sync_web_push_messages.py"
    )


def test_payload_is_localized_and_carries_no_secrets() -> None:
    payload = wp.build_payload(_notification(), locale="fr", badge=3)
    assert set(payload) == {"title", "body", "url", "badge"}
    assert payload["url"] == "/fr/account/orders/abc-123"
    assert payload["badge"] == 3
    assert "AB12CD" in payload["body"]
    assert payload["body"] != wp.build_payload(_notification(), locale="en", badge=3)["body"]
    serialized = json.dumps(payload)
    for secret in ("4321", "qr-secret", "pickup_pin", "qr_token", USER):
        assert secret not in serialized


def test_payload_falls_back_to_english_and_generic_text() -> None:
    en = wp.build_payload(_notification(), locale="en", badge=None)
    assert wp.build_payload(_notification(), locale="xx-YY", badge=None) == en
    assert en["badge"] is None
    # Unknown type or an unfillable placeholder never leaks raw "{ref}".
    unknown = wp.build_payload(
        _notification(i18n_key="notifications.inApp.customer.not_a_type"), locale="en", badge=0
    )
    no_ref = wp.build_payload(_notification(params={}), locale="en", badge=0)
    fallback = wp.load_messages()["en"]["inApp"]["fallback"]
    assert unknown["body"] == fallback == no_ref["body"]
    assert "{" not in no_ref["body"]


def test_payload_sanitizes_params_and_links() -> None:
    hostile = _notification(
        params={"ref": "<script>alert(1)</script>" + "x" * 80},
        link_path="//evil.test/phish",
        audience="vendor",
        i18n_key="notifications.inApp.vendor.order_placed",
    )
    payload = wp.build_payload(hostile, locale="en", badge=1)
    assert "<" not in payload["body"] and ">" not in payload["body"]
    assert payload["url"] == "/en/notifications"
    customer = wp.build_payload(_notification(link_path=None), locale="nya", badge=1)
    assert customer["url"] == "/nya/account/notifications"


@pytest.mark.parametrize(
    ("endpoint", "ok"),
    [
        (ENDPOINT, True),
        ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
        ("https://web.push.apple.com/abc", True),
        ("https://wns2-db5p.notify.windows.com/w/?token=x", True),
        ("http://fcm.googleapis.com/fcm/send/x", False),
        ("https://fcm.googleapis.com:8443/x", False),
        ("https://user:pw@fcm.googleapis.com/x", False),
        ("https://fcm.googleapis.com.evil.test/x", False),
        ("https://127.0.0.1/x", False),
    ],
)
def test_endpoint_allow_list(endpoint: str, ok: bool) -> None:
    assert wp.is_allowed_endpoint(endpoint) is ok


# --- transport ----------------------------------------------------------------------------
async def test_sender_encrypts_aes128gcm_and_signs_vapid() -> None:
    receiver, p256dh, auth_raw, auth = _receiver()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201)

    vapid = _vapid()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = wp.WebPushSender(vapid, client=client)
        outcome = await sender.send(endpoint=ENDPOINT, p256dh=p256dh, auth=auth, payload=b'{"t":1}')
    assert outcome == wp.SendOutcome(status_code=201)
    request = seen[0]
    assert request.headers["Content-Encoding"] == "aes128gcm"
    assert request.headers["TTL"] == str(wp.TTL_SECONDS)
    assert request.headers["Authorization"].startswith("vapid t=")
    assert f"k={vapid.public_key}" in request.headers["Authorization"]
    plain = http_ece.decrypt(
        request.content, private_key=receiver, auth_secret=auth_raw, version="aes128gcm"
    )
    assert plain == b'{"t":1}'


async def test_sender_reports_retry_after_and_never_calls_disallowed_hosts() -> None:
    _, p256dh, _, auth = _receiver()
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "120"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = wp.WebPushSender(_vapid(), client=client)
        limited = await sender.send(endpoint=ENDPOINT, p256dh=p256dh, auth=auth, payload=b"x")
        blocked = await sender.send(
            endpoint="https://169.254.169.254/x", p256dh=p256dh, auth=auth, payload=b"x"
        )
    assert limited == wp.SendOutcome(status_code=429, retry_after=120)
    assert blocked.error == "endpoint_not_allowed"
    assert calls == 1


# --- queue processing ---------------------------------------------------------------------
async def test_201_marks_sent_with_localized_payload() -> None:
    st, send = _store(locale="bem"), Recorder()
    stats = await _dispatcher(st, send).run(now=NOW)
    assert stats.sent == 1
    row = _delivery(st)
    assert row["status"] == "sent" and row["attempts"] == 1 and row["last_status_code"] == 201
    payload = json.loads(send.calls[0]["payload"])
    assert payload["url"].startswith("/bem/account/orders/")
    assert payload["body"] == wp.build_payload(_notification(), locale="bem", badge=1)["body"]
    assert payload["badge"] == 1
    assert "4321" not in send.calls[0]["payload"].decode()


async def test_second_tick_is_idempotent() -> None:
    st, send = _store(), Recorder()
    await _dispatcher(st, send).run(now=NOW)
    await _dispatcher(st, send).run(now=NOW + timedelta(minutes=10))
    assert len(send.calls) == 1


async def test_claim_is_compare_and_set_on_attempts() -> None:
    """A concurrent tick that already bumped attempts wins; we do not send."""
    st, send = _store(), Recorder()
    dispatcher = _dispatcher(st, send)
    due = dispatcher._due(NOW)
    _delivery(st)["attempts"] = 1  # the other worker claimed it first
    assert dispatcher._claim(due[0], NOW) is None
    assert send.calls == []


@pytest.mark.parametrize("code", [404, 410])
async def test_gone_subscription_is_deleted(code: int) -> None:
    st = _store()
    st.table("web_push_subscriptions").rows.append(
        {
            "id": "sub-2",
            "user_id": OTHER,
            "audience": "customer",
            "endpoint": "https://fcm.googleapis.com/x",
        }
    )
    stats = await _dispatcher(st, Recorder(wp.SendOutcome(status_code=code))).run(now=NOW)
    assert stats.gone == 1
    assert [s["id"] for s in st.table("web_push_subscriptions").rows] == ["sub-2"]


@pytest.mark.parametrize(
    ("outcome", "min_delay"),
    [
        (wp.SendOutcome(status_code=429, retry_after=900), 900),
        (wp.SendOutcome(status_code=503), wp.BACKOFF_BASE_SECONDS),
        (wp.SendOutcome(status_code=None, error="network_error"), wp.BACKOFF_BASE_SECONDS),
    ],
)
async def test_retryable_failures_back_off(outcome: wp.SendOutcome, min_delay: int) -> None:
    st = _store()
    stats = await _dispatcher(st, Recorder(outcome)).run(now=NOW)
    assert stats.retried == 1
    row = _delivery(st)
    assert row["status"] == "pending" and row["attempts"] == 1
    assert datetime.fromisoformat(row["next_attempt_at"]) >= NOW + timedelta(seconds=min_delay)


async def test_retries_are_exhausted_then_failed() -> None:
    st = _store(attempts=wp.MAX_ATTEMPTS - 1)
    stats = await _dispatcher(st, Recorder(wp.SendOutcome(status_code=500))).run(now=NOW)
    assert stats.failed == 1
    assert _delivery(st)["status"] == "failed"


async def test_other_4xx_is_terminal() -> None:
    st = _store()
    stats = await _dispatcher(st, Recorder(wp.SendOutcome(status_code=400))).run(now=NOW)
    assert stats.failed == 1 and _delivery(st)["status"] == "failed"
    assert len(st.table("web_push_subscriptions").rows) == 1


async def test_backoff_grows_and_is_capped() -> None:
    assert wp.backoff_seconds(1) == 60
    assert wp.backoff_seconds(3) == 240
    assert wp.backoff_seconds(30) == wp.MAX_BACKOFF_SECONDS


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda st: st.table("in_app_notifications").rows[0].update(seen_at=NOW.isoformat()),
            "already_seen",
        ),
        (
            lambda st: (
                st.table("in_app_notifications")
                .rows[0]
                .update(created_at=(NOW - timedelta(hours=13)).isoformat())
            ),
            "stale",
        ),
        (
            lambda st: st.table("web_push_subscriptions").rows[0].update(user_id=OTHER),
            "owner_changed",
        ),
        (lambda st: st.table("web_push_subscriptions").rows.clear(), "gone"),
    ],
)
async def test_skips_without_sending(mutate: Any, reason: str) -> None:
    st, send = _store(), Recorder()
    mutate(st)
    stats = await _dispatcher(st, send).run(now=NOW)
    assert stats.skipped == 1 and send.calls == []
    assert _delivery(st)["status"] == "skipped" and _delivery(st)["last_error"] == reason


async def test_per_user_rate_limit_skips() -> None:
    st, send = _store(), Recorder()
    stats = await _dispatcher(st, send, rate_limiter=lambda _u: False).run(now=NOW)
    assert stats.skipped == 1 and send.calls == []
    assert _delivery(st)["last_error"] == "rate_limited"


async def test_default_rate_limiter_uses_bump_rate_counter() -> None:
    st, send = _store(), Recorder()
    st.allow = False
    stats = await wp.WebPushDispatcher(st, send).run(now=NOW)
    assert stats.skipped == 1 and send.calls == []


async def test_quiet_hours_defer_to_morning_in_lusaka() -> None:
    st, send = _store(), Recorder()
    late = datetime(2026, 11, 13, 21, 30, tzinfo=UTC)  # 23:30 in Lusaka
    stats = await _dispatcher(st, send, quiet_hours=wp.QuietHours(22, 6)).run(now=late)
    assert stats.deferred == 1 and send.calls == []
    resume = datetime.fromisoformat(_delivery(st)["next_attempt_at"])
    assert resume == datetime(2026, 11, 14, 4, 0, tzinfo=UTC)  # 06:00 Lusaka
    assert _delivery(st)["attempts"] == 0


def test_quiet_hours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wp.QUIET_HOURS_ENV, raising=False)
    assert wp.QuietHours.from_env() == wp.QuietHours(22, 6, "Africa/Lusaka")
    monkeypatch.setenv(wp.QUIET_HOURS_ENV, "off")
    assert wp.QuietHours.from_env() is None
    monkeypatch.setenv(wp.QUIET_HOURS_ENV, "21-7")
    quiet = wp.QuietHours.from_env()
    assert quiet is not None and quiet.active(datetime(2026, 11, 13, 4, 30, tzinfo=UTC))
    assert not quiet.active(NOW)


# --- fail closed --------------------------------------------------------------------------
def _set_vapid(monkeypatch: pytest.MonkeyPatch, config: wp.VapidConfig | None) -> None:
    for name, value in (
        (wp.VAPID_PUBLIC_ENV, config.public_key if config else None),
        (wp.VAPID_PRIVATE_ENV, config.private_key if config else None),
        (wp.VAPID_SUBJECT_ENV, config.subject if config else None),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


async def test_flag_off_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vapid(monkeypatch, _vapid())
    st, send = _store(flag=False), Recorder()
    stats = await wp.run_web_push_batch(st, sender_factory=lambda _c: send, now=NOW)
    assert stats.reason == "flag_off" and send.calls == []
    assert _delivery(st)["status"] == "pending"


async def test_missing_vapid_env_fails_closed_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_vapid(monkeypatch, None)
    monkeypatch.setenv(wp.VAPID_PUBLIC_ENV, "public-placeholder")
    st, send = _store(), Recorder()
    with caplog.at_level("WARNING"):
        stats = await wp.run_web_push_batch(st, sender_factory=lambda _c: send, now=NOW)
    assert stats.reason == "vapid_missing" and send.calls == []
    assert "no alerts sent" in caplog.text


async def test_unusable_private_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vapid(monkeypatch, _vapid())
    monkeypatch.setenv(wp.VAPID_PRIVATE_ENV, "not-a-key")
    stats = await wp.run_web_push_batch(_store(), now=NOW)
    assert stats.reason == "vapid_invalid"


async def test_full_tick_with_generated_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vapid(monkeypatch, _vapid())
    monkeypatch.setenv(wp.QUIET_HOURS_ENV, "off")
    st, send = _store(), Recorder()
    stats = await wp.run_web_push_batch(st, sender_factory=lambda _c: send, now=NOW)
    assert stats.as_dict()["sent"] == 1


def test_tick_endpoint_requires_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app
    from fastapi.testclient import TestClient

    st = _store(flag=False)
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: st)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.post("/internal/dispatch/web-push-tick").status_code == 401
        ok = client.post(
            "/internal/dispatch/web-push-tick",
            headers={"X-Internal-Token": "dev-internal-dispatch"},
        )
    assert ok.status_code == 200 and ok.json()["reason"] == "flag_off"
