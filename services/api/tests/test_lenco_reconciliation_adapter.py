"""F3 Lenco reconciliation adapter tests over a real loopback HTTP socket."""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from app.services.payments.lenco.reconciliation import (
    LencoReconciliationAdapter,
    LencoReconciliationError,
)
from app.services.payments.reconciliation_matcher import (
    EvidenceOrigin,
    collect_provider_pages,
)


@contextmanager
def _provider_server(
    responses: dict[tuple[str, str | None], dict[str, Any]],
) -> Generator[tuple[str, list[dict[str, Any]]], None, None]:
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP hook
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            page = query.get("page", [None])[0]
            requests.append(
                {
                    "path": parsed.path,
                    "query": query,
                    "authorization": self.headers.get("Authorization"),
                }
            )
            body = responses.get((parsed.path, page))
            if body is None:
                self.send_response(404)
                body = {"status": False, "message": "missing synthetic route", "data": None}
            else:
                self.send_response(200)
            encoded = json.dumps(body).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = str(server.server_address[0])
        port = int(server.server_address[1])
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _accounts() -> dict[str, Any]:
    return {
        "status": True,
        "message": "ok",
        "data": [
            {
                "id": "account-wrong-first",
                "currency": "ZMW",
                "availableBalance": "999.00",
                "ledgerBalance": "999.00",
            },
            {
                "id": "account-configured",
                "currency": "ZMW",
                "availableBalance": "120.00",
                "ledgerBalance": "125.00",
            },
        ],
    }


def _transaction(transaction_id: str, reference: str, amount: str) -> dict[str, Any]:
    return {
        "id": transaction_id,
        "amount": amount,
        "currency": "ZMW",
        "narration": f"Transfer / {reference}",
        "type": "credit",
        "datetime": "2026-09-29T12:00:00Z",
        "accountId": "account-configured",
        "balance": "125.00",
    }


def _page(number: int, count: int, total: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": True,
        "message": "ok",
        "data": rows,
        "meta": {
            "total": total,
            "perPage": 1,
            "currentPage": number,
            "pageCount": count,
        },
    }


@pytest.mark.asyncio
async def test_adapter_selects_configured_account_and_walks_every_declared_page() -> None:
    responses = {
        ("/accounts", None): _accounts(),
        ("/transactions", "1"): _page(
            1, 2, 2, [_transaction("txn-1", "lenco-one", "10.00")]
        ),
        ("/transactions", "2"): _page(
            2, 2, 2, [_transaction("txn-2", "lenco-two", "15.00")]
        ),
    }
    with _provider_server(responses) as (base_url, requests):
        adapter = LencoReconciliationAdapter(
            configured_account_id="account-configured",
            token="synthetic-token",
            base_url=base_url,
            trust_env=False,
            evidence_origin=EvidenceOrigin.SYNTHETIC,
        )
        evidence = await adapter.collect(report_date=date(2026, 9, 29))
        await adapter.aclose()

    assert evidence.account.account_id == "account-configured"
    assert evidence.account.available_balance_ngwee == 12_000
    assert [page.page_number for page in evidence.pages] == [1, 2]
    assert all(page.raw_sha256 for page in evidence.pages)
    movements = [movement for page in evidence.pages for movement in page.movements]
    assert [movement.provider_reference for movement in movements] == [
        "lenco-one",
        "lenco-two",
    ]
    assert [movement.running_balance_ngwee for movement in movements] == [12500, 12500]
    assert all(movement.merchant_reference is None for movement in movements)
    assert all(
        movement.provider_reference_source == "transaction.narration"
        for movement in movements
    )
    assert all(movement.evidence_origin == EvidenceOrigin.SYNTHETIC for movement in movements)
    assert [request["query"].get("page") for request in requests[1:]] == [["1"], ["2"]]
    assert all(request["authorization"] == "Bearer synthetic-token" for request in requests)


@pytest.mark.asyncio
async def test_missing_pagination_meta_is_incomplete_not_assumed_single_page() -> None:
    responses = {
        ("/accounts", None): _accounts(),
        ("/transactions", "1"): {
            "status": True,
            "message": "ok",
            "data": [_transaction("txn-1", "lenco-one", "10.00")],
        },
    }
    with _provider_server(responses) as (base_url, _requests):
        adapter = LencoReconciliationAdapter(
            configured_account_id="account-configured",
            token="synthetic-token",
            base_url=base_url,
            trust_env=False,
            evidence_origin=EvidenceOrigin.SYNTHETIC,
        )
        evidence = await adapter.collect(report_date=date(2026, 9, 29))
        await adapter.aclose()

    collected = collect_provider_pages(
        evidence.pages,
        configured_account_id="account-configured",
        currency="ZMW",
        cutoff_utc=datetime.fromisoformat("2026-09-29T23:59:59+00:00"),
    )
    assert not collected.complete
    assert any("pagination metadata missing" in issue for issue in collected.issues)
    assert any("envelope is missing meta" in issue for issue in collected.issues)


@pytest.mark.asyncio
async def test_200_false_envelope_and_wrong_account_fail_closed() -> None:
    false_responses: dict[tuple[str, str | None], dict[str, Any]] = {
        ("/accounts", None): {"status": False, "message": "auth denied", "data": None}
    }
    with _provider_server(false_responses) as (base_url, _requests):
        adapter = LencoReconciliationAdapter(
            configured_account_id="account-configured",
            token="synthetic-token",
            base_url=base_url,
            trust_env=False,
            evidence_origin=EvidenceOrigin.SYNTHETIC,
        )
        with pytest.raises(LencoReconciliationError, match="auth denied"):
            await adapter.collect(report_date=date(2026, 9, 29))
        await adapter.aclose()

    wrong_responses: dict[tuple[str, str | None], dict[str, Any]] = {
        ("/accounts", None): _accounts()
    }
    with _provider_server(wrong_responses) as (base_url, _requests):
        adapter = LencoReconciliationAdapter(
            configured_account_id="account-missing",
            token="synthetic-token",
            base_url=base_url,
            trust_env=False,
            evidence_origin=EvidenceOrigin.SYNTHETIC,
        )
        with pytest.raises(LencoReconciliationError, match="matched 0 rows"):
            await adapter.collect(report_date=date(2026, 9, 29))
        await adapter.aclose()


@pytest.mark.asyncio
async def test_schema_error_is_retained_on_the_page_and_cannot_certify() -> None:
    malformed = _transaction("txn-1", "lenco-one", "10.00")
    malformed.pop("accountId")
    responses = {
        ("/accounts", None): _accounts(),
        ("/transactions", "1"): _page(1, 1, 1, [malformed]),
    }
    with _provider_server(responses) as (base_url, _requests):
        adapter = LencoReconciliationAdapter(
            configured_account_id="account-configured",
            token="synthetic-token",
            base_url=base_url,
            trust_env=False,
            evidence_origin=EvidenceOrigin.SYNTHETIC,
        )
        evidence = await adapter.collect(report_date=date(2026, 9, 29))
        await adapter.aclose()

    collected = collect_provider_pages(
        evidence.pages,
        configured_account_id="account-configured",
        currency="ZMW",
        cutoff_utc=datetime.fromisoformat("2026-09-29T23:59:59+00:00"),
    )
    assert not collected.complete
    assert any("transaction.accountId" in issue for issue in collected.issues)
    assert any("total mismatch" in issue for issue in collected.issues)
