"""Unit tests for Upstash/in-memory OTP per-number rate limiting."""

from __future__ import annotations

import pytest
from app.core.otp_ratelimit import (
    OTP_CAP_PER_NUMBER,
    OTP_WINDOW_SECONDS,
    InMemoryOtpRedisStore,
    check_otp_number_rate_limit,
    clear_otp_redis_store_cache,
    otp_number_key,
)
from app.core.ratelimit import check_and_increment_otp_quota, raise_rate_limited
from app.errors import AppError


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    clear_otp_redis_store_cache()
    yield
    clear_otp_redis_store_cache()


def test_otp_number_key_is_stable() -> None:
    assert otp_number_key("+260971234567") == "otp:number:+260971234567"


def test_in_memory_allows_up_to_cap() -> None:
    store = InMemoryOtpRedisStore()
    phone = "+260971234567"
    for expected in range(1, OTP_CAP_PER_NUMBER + 1):
        allowed, retry_after, count = check_otp_number_rate_limit(
            phone=phone,
            store=store,
        )
        assert allowed is True
        assert retry_after == 0
        assert count == expected


def test_in_memory_blocks_fourth_request_within_window() -> None:
    store = InMemoryOtpRedisStore()
    phone = "+260972222222"
    for _ in range(OTP_CAP_PER_NUMBER):
        check_otp_number_rate_limit(phone=phone, store=store)

    allowed, retry_after, count = check_otp_number_rate_limit(phone=phone, store=store)
    assert allowed is False
    assert retry_after >= 1
    assert count == OTP_CAP_PER_NUMBER + 1


def test_in_memory_per_phone_independence() -> None:
    store = InMemoryOtpRedisStore()
    for _ in range(OTP_CAP_PER_NUMBER):
        check_otp_number_rate_limit(phone="+260973333333", store=store)

    blocked, _, _ = check_otp_number_rate_limit(phone="+260973333333", store=store)
    other_allowed, _, _ = check_otp_number_rate_limit(phone="+260974444444", store=store)
    assert blocked is False
    assert other_allowed is True


def test_raise_rate_limited_uses_auth_message_key() -> None:
    with pytest.raises(AppError) as exc:
        raise_rate_limited(
            retry_after=42,
            message_key="auth.errors.otp_number_limit",
        )
    assert exc.value.http_status == 429
    assert exc.value.details["message_key"] == "auth.errors.otp_number_limit"
    assert exc.value.details["retry_after"] == 42


def test_check_and_increment_otp_quota_blocks_after_redis_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_ratelimit import FakeSupabaseClient

    fake_client = FakeSupabaseClient()
    monkeypatch.setattr(
        "app.core.ratelimit.check_active_cooldown",
        lambda **kwargs: (True, 0),
    )
    monkeypatch.setattr(
        "app.core.ratelimit.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )
    monkeypatch.setattr(
        "app.core.ratelimit.record_resend_cooldown",
        lambda **kwargs: 30,
    )

    phone = "+260975555555"
    for _ in range(OTP_CAP_PER_NUMBER):
        check_and_increment_otp_quota(phone=phone, ip="203.0.113.1", client=fake_client)

    with pytest.raises(AppError) as exc:
        check_and_increment_otp_quota(phone=phone, ip="203.0.113.1", client=fake_client)

    assert exc.value.code == "rate_limited"
    assert exc.value.details["message_key"] == "auth.errors.otp_number_limit"
    assert exc.value.details["retry_after"] >= 1


def test_window_seconds_is_fifteen_minutes() -> None:
    assert OTP_WINDOW_SECONDS == 900
