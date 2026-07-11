"""Signed owner-scoped invoice download + VAT-flag-aware PDF render (M15-P07)."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.invoices import sign_invoice_token
from app.services.invoicing.builder import InvoiceInputLine, build_invoice_payload
from app.services.invoicing.pdf import format_k, render_invoice_pdf
from app.services.invoicing.vsdc import submit_to_vsdc_stub
from fastapi.testclient import TestClient

CUSTOMER_A_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_OWNER = "99999999-9999-9999-9999-999999999999"
VENDOR_B_OWNER = "88888888-8888-8888-8888-888888888888"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ORDER_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"


# --------------------------------------------------------------------------- fakes


class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False
        self._limit: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def _filtered(self) -> list[dict[str, Any]]:
        rows = self._rows
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def execute(self) -> MagicMock:
        rows = self._filtered()
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return FakeQuery(self.rows)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "vendors": FakeTable(),
            "invoices": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]

    def rpc(self, _name: str, _params: dict[str, Any]) -> MagicMock:
        execute = MagicMock()
        execute.execute.return_value = MagicMock(
            data=[{"allowed": True, "retry_after_seconds": 0}]
        )
        return execute


def _snapshot(*, series: str, invoice_no: int, kind: str) -> dict[str, Any]:
    payload = build_invoice_payload(
        kind=kind,  # type: ignore[arg-type]
        series=series,
        invoice_no=invoice_no,
        order_id=ORDER_A_ID,
        lines=(InvoiceInputLine(description="Solar lamp", qty=2, unit_price_ngwee=25_000),),
        seller_tpin="1000000000",
        vat_flag=False,
    )
    return payload.to_snapshot()


def _seed(fake: FakeSupabase) -> None:
    fake.tables["orders"].rows.append(
        {"id": ORDER_A_ID, "customer_id": CUSTOMER_A_ID, "vendor_id": VENDOR_A_ID}
    )
    fake.tables["vendors"].rows.extend(
        [
            {"id": VENDOR_A_ID, "owner_user_id": VENDOR_A_OWNER},
            {"id": VENDOR_B_ID, "owner_user_id": VENDOR_B_OWNER},
        ]
    )
    fake.tables["invoices"].rows.extend(
        [
            {
                "id": "inv-tax",
                "series": "TAX",
                "no": 42,
                "order_id": ORDER_A_ID,
                "snapshot": _snapshot(series="TAX", invoice_no=42, kind="tax_invoice"),
                "created_at": "2026-07-10T10:00:00Z",
            },
            {
                "id": "inv-rcp",
                "series": "RCP",
                "no": 7,
                "order_id": ORDER_A_ID,
                "snapshot": _snapshot(series="RCP", invoice_no=7, kind="receipt"),
                "created_at": "2026-07-10T09:00:00Z",
            },
        ]
    )


def _mock_auth(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"customer"}),
    )


def _client(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase, user_id: str) -> TestClient:
    _mock_auth(monkeypatch, user_id)
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: wrapper)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def fake() -> FakeSupabase:
    instance = FakeSupabase()
    _seed(instance)
    return instance


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


# --------------------------------------------------------------------------- render


class TestRender:
    def test_format_k_integer_only(self) -> None:
        assert format_k(123_456) == "K1,234.56"
        assert format_k(0) == "K0.00"
        assert format_k(5) == "K0.05"

    def test_pdf_renders_with_sequential_number(self) -> None:
        snapshot = _snapshot(series="TAX", invoice_no=42, kind="tax_invoice")
        pdf = render_invoice_pdf(snapshot)
        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > 200
        assert b"TAX-000042" in pdf

    def test_vat_block_absent_when_flag_off(self) -> None:
        snapshot = _snapshot(series="TAX", invoice_no=1, kind="tax_invoice")
        assert snapshot["vat_flag"] is False
        pdf = render_invoice_pdf(snapshot)  # defaults to snapshot vat_flag (off)
        assert b"VAT:" not in pdf
        assert b"Turnover Tax" in pdf

    def test_vat_block_present_when_flag_on(self) -> None:
        snapshot = _snapshot(series="TAX", invoice_no=1, kind="tax_invoice")
        pdf = render_invoice_pdf(snapshot, vat_enabled=True)
        assert b"VAT:" in pdf

    def test_vsdc_seam_is_stub_only(self) -> None:
        snapshot = _snapshot(series="TAX", invoice_no=42, kind="tax_invoice")
        result = submit_to_vsdc_stub(snapshot)
        assert result.submitted is False
        assert result.fiscal_code == "VSDC-STUB-TAX-42"


# --------------------------------------------------------------------------- download


class TestDownload:
    def test_customer_owner_downloads_pdf(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, CUSTOMER_A_ID)
        resp = client.get(f"/invoices/{ORDER_A_ID}", headers=_headers())
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF-")
        assert b"TAX-000042" in resp.content

    def test_receipt_vs_tax_invoice_variant(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, CUSTOMER_A_ID)
        tax = client.get(f"/invoices/{ORDER_A_ID}?kind=tax_invoice", headers=_headers())
        receipt = client.get(f"/invoices/{ORDER_A_ID}?kind=receipt", headers=_headers())
        assert tax.status_code == 200
        assert receipt.status_code == 200
        assert b"TAX-000042" in tax.content
        assert b"RCP-000007" in receipt.content
        assert b"RECEIPT" in receipt.content

    def test_vendor_owner_downloads_pdf(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, VENDOR_A_OWNER)
        resp = client.get(f"/invoices/{ORDER_A_ID}", headers=_headers())
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-")

    def test_idor_other_customer_gets_404(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, CUSTOMER_B_ID)
        resp = client.get(f"/invoices/{ORDER_A_ID}", headers=_headers())
        assert resp.status_code == 404

    def test_idor_other_vendor_gets_404(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, VENDOR_B_OWNER)
        resp = client.get(f"/invoices/{ORDER_A_ID}", headers=_headers())
        assert resp.status_code == 404


# --------------------------------------------------------------------------- signed url


class TestSignedUrl:
    def test_signed_url_roundtrip(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, CUSTOMER_A_ID)
        minted = client.get(f"/invoices/{ORDER_A_ID}/signed-url", headers=_headers())
        assert minted.status_code == 200
        download_url = minted.json()["download_url"]
        # Public follow (no bearer) must succeed for a valid token.
        resp = client.get(download_url)
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-")

    def test_tampered_token_forbidden(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, CUSTOMER_A_ID)
        token = sign_invoice_token(
            order_id=ORDER_A_ID,
            subject_id=CUSTOMER_A_ID,
            role="customer",
            expires_at=int(time.time()) + 600,
        )
        tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
        resp = client.get(f"/invoices/download?order_id={ORDER_A_ID}&token={tampered}")
        assert resp.status_code == 403

    def test_signed_url_non_owner_404(
        self, monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase
    ) -> None:
        client = _client(monkeypatch, fake, CUSTOMER_B_ID)
        resp = client.get(f"/invoices/{ORDER_A_ID}/signed-url", headers=_headers())
        assert resp.status_code == 404
