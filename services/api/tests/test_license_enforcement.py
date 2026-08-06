"""Unit tests for regulator licence expiry enforcement (no live DB)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.services.vendors.license_enforcement import (
    ExpiredLicenceTarget,
    enforce_expired_licence,
    list_expired_licence_targets,
)


def test_list_expired_licence_targets_parses_rows() -> None:
    with patch("app.services.vendors.license_enforcement.run_sql_script") as run_mock:
        run_mock.return_value.ok = True
        run_mock.return_value.error = None
        run_mock.return_value.rows = [
            "vendor-a|licence-1|pharmacy|2026-08-05|HPCZ",
        ]

        targets = list_expired_licence_targets(today=date(2026, 8, 6))

    assert len(targets) == 1
    assert targets[0].vendor_id == "vendor-a"
    assert targets[0].licence_id == "licence-1"
    assert targets[0].expiry_date == "2026-08-05"
    assert targets[0].license_body == "HPCZ"


def test_enforce_expired_licence_returns_counts() -> None:
    target = ExpiredLicenceTarget(
        vendor_id="vendor-a",
        licence_id="licence-1",
        regulated_class="pharmacy",
        expiry_date="2026-08-05",
        license_body="HPCZ",
    )
    with patch("app.services.vendors.license_enforcement.run_sql_script") as run_mock:
        run_mock.return_value.ok = True
        run_mock.return_value.error = None
        run_mock.return_value.rows = ["1|2|1"]

        result = enforce_expired_licence(target, today=date(2026, 8, 6))

    assert result.vendor_suspended is True
    assert result.listings_removed == 2
    assert result.audited is True
    script = run_mock.call_args.args[0]
    assert "suspended_compliance" in script
    assert "compliance.license_expired_suspend" in script
    assert "status = 'removed'" in script
