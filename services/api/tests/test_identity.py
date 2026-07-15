"""Tests for auth.users email lookup via the service-role admin API."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.identity import lookup_user_email

USER_ID = "11111111-1111-1111-1111-111111111111"


class _FakeAdmin:
    def __init__(self, *, response: Any = None, raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.calls: list[str] = []

    def get_user_by_id(self, user_id: str) -> Any:
        self.calls.append(user_id)
        if self._raises is not None:
            raise self._raises
        return self._response


class _FakeClient:
    def __init__(self, admin: _FakeAdmin) -> None:
        self.auth = SimpleNamespace(admin=admin)


class _FakeService:
    def __init__(self, admin: _FakeAdmin) -> None:
        self._client = _FakeClient(admin)

    @property
    def client(self) -> _FakeClient:
        return self._client


def _service(*, response: Any = None, raises: Exception | None = None) -> _FakeService:
    return _FakeService(_FakeAdmin(response=response, raises=raises))


def test_returns_stripped_email_on_success() -> None:
    user = SimpleNamespace(email="  Buyer@Example.com  ")
    service = _service(response=SimpleNamespace(user=user))
    assert lookup_user_email(service, user_id=USER_ID) == "Buyer@Example.com"


def test_returns_none_when_email_missing() -> None:
    service = _service(response=SimpleNamespace(user=SimpleNamespace(email=None)))
    assert lookup_user_email(service, user_id=USER_ID) is None


def test_returns_none_when_email_blank() -> None:
    service = _service(response=SimpleNamespace(user=SimpleNamespace(email="   ")))
    assert lookup_user_email(service, user_id=USER_ID) is None


def test_returns_none_when_no_user() -> None:
    service = _service(response=SimpleNamespace(user=None))
    assert lookup_user_email(service, user_id=USER_ID) is None


def test_swallows_admin_api_error() -> None:
    service = _service(raises=RuntimeError("gotrue unavailable"))
    assert lookup_user_email(service, user_id=USER_ID) is None


def test_empty_user_id_short_circuits() -> None:
    admin = _FakeAdmin(response=SimpleNamespace(user=SimpleNamespace(email="x@y.com")))
    service = _FakeService(admin)
    assert lookup_user_email(service, user_id="") is None
    assert admin.calls == []  # never calls the admin API with an empty id
