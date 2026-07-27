"""M18-P00 — fail-closed config seam for the WAHA vendor-intake lane (D35).

Every test here asserts the same property from a different angle: **the lane is
never open by accident**. A missing row, an unreadable table, a malformed
allowlist, or an unset secret must all resolve to "off" / "raise", never to a
silent default.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.intake import config as intake_config

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

ALL_SECRET_ENVS = (
    intake_config.ENV_BASE_URL,
    intake_config.ENV_API_KEY,
    intake_config.ENV_SESSION,
    intake_config.ENV_WEBHOOK_SECRET,
    intake_config.ENV_ALLOWED_IPS,
    intake_config.ENV_SENDER_E164,
)


# ---------------------------------------------------------------------------
# Minimal Supabase double — only what config.py touches.
# ---------------------------------------------------------------------------
class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]], raises: bool) -> None:
        self._rows = rows
        self._raises = raises
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> MagicMock:
        if self._raises:
            raise RuntimeError("supabase unreachable")
        rows = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters)]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]], raises: bool = False) -> None:
        self._tables = tables
        self._raises = raises

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self._tables.get(name, []), self._raises)


class FakeServiceClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]], raises: bool = False) -> None:
        self.client = FakeClient(tables, raises)


def _client(
    *,
    enabled: bool | None = None,
    allowlist: Any = None,
    raises: bool = False,
) -> FakeServiceClient:
    tables: dict[str, list[dict[str, Any]]] = {"feature_flags": [], "platform_config": []}
    if enabled is not None:
        tables["feature_flags"] = [
            {"flag": intake_config.INTAKE_FLAG, "enabled": enabled}
        ]
    if allowlist is not None:
        tables["platform_config"] = [
            {"key": intake_config.INTAKE_ALLOWLIST_KEY, "value": allowlist}
        ]
    return FakeServiceClient(tables, raises)


# ---------------------------------------------------------------------------
# The kill switch defaults to off
# ---------------------------------------------------------------------------
def test_flag_row_missing_disables_lane() -> None:
    """No row at all — the lane must be off, not open."""
    assert intake_config.intake_enabled(_client()) is False


def test_flag_false_disables_lane() -> None:
    assert intake_config.intake_enabled(_client(enabled=False)) is False


def test_flag_true_enables_lane() -> None:
    assert intake_config.intake_enabled(_client(enabled=True)) is True


def test_read_error_fails_closed_without_raising() -> None:
    """A DB outage must disable the lane, not surface an exception to the caller.

    If this raised, the webhook's first gate would 500 instead of dropping —
    turning a config blip into a probe-able signal.
    """
    assert intake_config.intake_enabled(_client(enabled=True, raises=True)) is False


def test_flag_is_read_fresh_every_call() -> None:
    """The kill switch must not be defeated by caching."""
    tables: dict[str, list[dict[str, Any]]] = {
        "feature_flags": [{"flag": intake_config.INTAKE_FLAG, "enabled": True}],
        "platform_config": [],
    }
    client = FakeServiceClient(tables)
    assert intake_config.intake_enabled(client) is True

    tables["feature_flags"][0]["enabled"] = False
    assert intake_config.intake_enabled(client) is False


# ---------------------------------------------------------------------------
# "On" never means "open to everyone"
# ---------------------------------------------------------------------------
def test_empty_allowlist_admits_nobody() -> None:
    client = _client(enabled=True, allowlist=[])
    assert intake_config.intake_enabled(client) is True
    assert intake_config.vendor_allowlisted(client, VENDOR_A) is False


def test_missing_allowlist_row_admits_nobody() -> None:
    assert intake_config.vendor_allowlisted(_client(enabled=True), VENDOR_A) is False


def test_allowlisted_vendor_admitted_others_are_not() -> None:
    client = _client(enabled=True, allowlist=[VENDOR_A])
    assert intake_config.vendor_allowlisted(client, VENDOR_A) is True
    assert intake_config.vendor_allowlisted(client, VENDOR_B) is False


def test_allowlist_accepts_json_encoded_value() -> None:
    """Some drivers hand back jsonb as raw text; both shapes must work."""
    client = _client(enabled=True, allowlist=json.dumps([VENDOR_A]))
    assert intake_config.vendor_allowlisted(client, VENDOR_A) is True


@pytest.mark.parametrize("bad", ["not json", '{"not": "a list"}', 42, {"a": 1}, None])
def test_malformed_allowlist_admits_nobody(bad: Any) -> None:
    client = _client(enabled=True, allowlist=bad)
    assert intake_config.vendor_allowlisted(client, VENDOR_A) is False


def test_allowlist_read_error_admits_nobody() -> None:
    client = _client(enabled=True, allowlist=[VENDOR_A], raises=True)
    assert intake_config.vendor_allowlisted(client, VENDOR_A) is False


@pytest.mark.parametrize("vendor_id", ["", "   "])
def test_blank_vendor_id_never_allowlisted(vendor_id: str) -> None:
    client = _client(enabled=True, allowlist=[VENDOR_A, ""])
    assert intake_config.vendor_allowlisted(client, vendor_id) is False


def test_lane_open_for_requires_both_gates() -> None:
    flag_off = _client(enabled=False, allowlist=[VENDOR_A])
    not_listed = _client(enabled=True, allowlist=[])
    both = _client(enabled=True, allowlist=[VENDOR_A])
    assert intake_config.lane_open_for(flag_off, VENDOR_A) is False
    assert intake_config.lane_open_for(not_listed, VENDOR_A) is False
    assert intake_config.lane_open_for(both, VENDOR_A) is True


# ---------------------------------------------------------------------------
# Secrets never default
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("accessor", "env_name"),
    [
        (intake_config.base_url, intake_config.ENV_BASE_URL),
        (intake_config.api_key, intake_config.ENV_API_KEY),
        (intake_config.session_name, intake_config.ENV_SESSION),
        (intake_config.webhook_secret, intake_config.ENV_WEBHOOK_SECRET),
        (intake_config.allowed_ips, intake_config.ENV_ALLOWED_IPS),
        (intake_config.sender_e164, intake_config.ENV_SENDER_E164),
    ],
)
def test_unset_env_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, accessor: Any, env_name: str
) -> None:
    """Unset must raise 503, never return a default or a Lane 1 value."""
    monkeypatch.delenv(env_name, raising=False)
    with pytest.raises(AppError) as exc:
        accessor()
    assert exc.value.code == "configuration_error"
    assert exc.value.http_status == 503
    assert exc.value.details.get("missing") == env_name


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_env_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    monkeypatch.setenv(intake_config.ENV_WEBHOOK_SECRET, blank)
    with pytest.raises(AppError):
        intake_config.webhook_secret()


def test_secret_value_never_appears_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure names the missing variable, never leaks a neighbouring value."""
    monkeypatch.setenv(intake_config.ENV_API_KEY, "super-secret-key")
    monkeypatch.delenv(intake_config.ENV_WEBHOOK_SECRET, raising=False)
    with pytest.raises(AppError) as exc:
        intake_config.webhook_secret()
    assert "super-secret-key" not in json.dumps(exc.value.details)
    assert "super-secret-key" not in exc.value.message


def test_intake_envs_do_not_fall_back_to_lane_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rotating WAHA_INTAKE_* must never be satisfied by a WHATSAPP_*/LENCO_* value."""
    monkeypatch.setenv("WHATSAPP_TOKEN", "lane1-token")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "lane1-secret")
    monkeypatch.setenv("LENCO_API_KEY", "lenco-key")
    for name in ALL_SECRET_ENVS:
        monkeypatch.delenv(name, raising=False)

    for accessor in (
        intake_config.base_url,
        intake_config.api_key,
        intake_config.session_name,
        intake_config.webhook_secret,
        intake_config.allowed_ips,
        intake_config.sender_e164,
    ):
        with pytest.raises(AppError):
            accessor()


def test_allowed_ips_splits_on_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(intake_config.ENV_ALLOWED_IPS, "10.0.0.1/32  10.0.0.2/32")
    assert intake_config.allowed_ips() == ["10.0.0.1/32", "10.0.0.2/32"]


# ---------------------------------------------------------------------------
# NB-7 — the intake number must be provably different from Lane 1's
# ---------------------------------------------------------------------------
def test_sender_separation_fails_when_numbers_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(intake_config.ENV_SENDER_E164, "+260971234567")
    monkeypatch.setenv("WHATSAPP_SENDER_E164", "260971234567")
    assert intake_config.sender_separation_ok() is False
    with pytest.raises(AppError):
        intake_config.assert_sender_separation()


def test_sender_separation_ok_when_numbers_differ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(intake_config.ENV_SENDER_E164, "+260971234567")
    monkeypatch.setenv("WHATSAPP_SENDER_E164", "+260979999999")
    assert intake_config.sender_separation_ok() is True
    intake_config.assert_sender_separation()


def test_sender_separation_fails_closed_when_lane1_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unprovable separation is not the same as proven separation."""
    monkeypatch.setenv(intake_config.ENV_SENDER_E164, "+260971234567")
    monkeypatch.delenv("WHATSAPP_SENDER_E164", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    assert intake_config.sender_separation_ok() is False


def test_sender_separation_fails_closed_when_intake_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(intake_config.ENV_SENDER_E164, raising=False)
    monkeypatch.setenv("WHATSAPP_SENDER_E164", "+260979999999")
    assert intake_config.sender_separation_ok() is False


# ---------------------------------------------------------------------------
# Boundary: this module is inbound-only and holds no outbound client
# ---------------------------------------------------------------------------
def test_module_exposes_no_send_capability() -> None:
    """D35: strictly inbound-only — no ack, no reply, no outbound of any kind.

    Guards against a future edit quietly adding a sender to the config seam.
    """
    exported = dir(intake_config)
    for forbidden in ("send", "send_message", "post_message", "ack", "acknowledge", "reply"):
        assert forbidden not in exported
