from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.routers.privacy import verify_reauth_otp


def _settings() -> Any:
    return type(
        "SettingsStub",
        (),
        {
            "supabase_url": "https://example.supabase.co",
            "supabase_anon_key": "anon",
        },
    )()


def test_verify_reauth_email_path(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    auth_client = MagicMock()
    auth_client.auth.verify_otp.return_value = MagicMock(
        session={"ok": True},
        user=MagicMock(id="user-1"),
    )

    monkeypatch.setattr("app.routers.privacy.bump_rate_counter", lambda **_: (True, 0))
    monkeypatch.setattr(
        "app.routers.privacy.lookup_confirmed_email",
        lambda _service, **_: "vendor@example.com",
    )
    monkeypatch.setattr("app.routers.privacy.create_client", lambda *_, **__: auth_client)

    verify_reauth_otp(
        user_id="user-1",
        token="jwt",
        phone=None,
        otp="123456",
        channel="email",
        settings=_settings(),
        service=service,
    )
    auth_client.auth.verify_otp.assert_called_once_with(
        {"email": "vendor@example.com", "token": "123456", "type": "email"},
    )


def test_verify_reauth_email_when_profile_has_phone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Email channel must be used even when profiles.phone is set (payout form sends email OTP)."""
    service = MagicMock()
    auth_client = MagicMock()
    auth_client.auth.verify_otp.return_value = MagicMock(
        session={"ok": True},
        user=MagicMock(id="user-1"),
    )

    monkeypatch.setattr("app.routers.privacy.bump_rate_counter", lambda **_: (True, 0))
    monkeypatch.setattr(
        "app.routers.privacy.lookup_confirmed_email",
        lambda _service, **_: "vendor@example.com",
    )
    monkeypatch.setattr("app.routers.privacy.create_client", lambda *_, **__: auth_client)

    verify_reauth_otp(
        user_id="user-1",
        token="jwt",
        phone="+260971234567",
        otp="123456",
        channel="email",
        settings=_settings(),
        service=service,
    )
    auth_client.auth.verify_otp.assert_called_once_with(
        {"email": "vendor@example.com", "token": "123456", "type": "email"},
    )


def test_verify_reauth_sms_path(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    auth_client = MagicMock()
    auth_client.auth.verify_otp.return_value = MagicMock(
        session={"ok": True},
        user=MagicMock(id="user-1"),
    )

    monkeypatch.setattr("app.routers.privacy.bump_rate_counter", lambda **_: (True, 0))
    monkeypatch.setattr("app.routers.privacy._phone_confirmed_for_user", lambda *_args, **_kw: True)
    monkeypatch.setattr("app.routers.privacy.create_client", lambda *_, **__: auth_client)

    verify_reauth_otp(
        user_id="user-1",
        token="jwt",
        phone="+260971234567",
        otp="654321",
        channel="sms",
        settings=_settings(),
        service=service,
    )
    auth_client.auth.verify_otp.assert_called_once_with(
        {"phone": "+260971234567", "token": "654321", "type": "sms"},
    )


def test_verify_reauth_requires_confirmed_email(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    monkeypatch.setattr("app.routers.privacy.bump_rate_counter", lambda **_: (True, 0))
    monkeypatch.setattr("app.routers.privacy.lookup_confirmed_email", lambda _service, **_: None)

    with pytest.raises(AppError) as exc:
        verify_reauth_otp(
            user_id="user-1",
            token="jwt",
            phone=None,
            otp="123456",
            channel="email",
            settings=_settings(),
            service=service,
        )
    assert exc.value.code == "reauth_required"


def test_verify_reauth_wrong_code(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    auth_client = MagicMock()
    auth_client.auth.verify_otp.return_value = MagicMock(session=None, user=None)

    monkeypatch.setattr("app.routers.privacy.bump_rate_counter", lambda **_: (True, 0))
    monkeypatch.setattr(
        "app.routers.privacy.lookup_confirmed_email",
        lambda _service, **_: "vendor@example.com",
    )
    monkeypatch.setattr("app.routers.privacy.create_client", lambda *_, **__: auth_client)

    with pytest.raises(AppError) as exc:
        verify_reauth_otp(
            user_id="user-1",
            token="jwt",
            phone=None,
            otp="000000",
            channel="email",
            settings=_settings(),
            service=service,
        )
    assert exc.value.code == "reauth_failed"


def test_verify_reauth_user_id_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    auth_client = MagicMock()
    auth_client.auth.verify_otp.return_value = MagicMock(
        session={"ok": True},
        user=MagicMock(id="other-user"),
    )

    monkeypatch.setattr("app.routers.privacy.bump_rate_counter", lambda **_: (True, 0))
    monkeypatch.setattr(
        "app.routers.privacy.lookup_confirmed_email",
        lambda _service, **_: "vendor@example.com",
    )
    monkeypatch.setattr("app.routers.privacy.create_client", lambda *_, **__: auth_client)

    with pytest.raises(AppError) as exc:
        verify_reauth_otp(
            user_id="user-1",
            token="jwt",
            phone=None,
            otp="123456",
            channel="email",
            settings=_settings(),
            service=service,
        )
    assert exc.value.code == "reauth_failed"


def test_verify_reauth_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    monkeypatch.setattr("app.routers.privacy.bump_rate_counter", lambda **_: (False, 30))

    with pytest.raises(AppError) as exc:
        verify_reauth_otp(
            user_id="user-1",
            token="jwt",
            phone=None,
            otp="123456",
            channel="email",
            settings=_settings(),
            service=service,
        )
    assert exc.value.code == "rate_limited"