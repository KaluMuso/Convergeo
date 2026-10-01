"""Protected local evidence reader for the F3 daily reconciliation report."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol, cast

from app.services.payments.reconciliation_matcher import LocalMovement, MovementKind


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class LocalReconciliationEvidence:
    movements: tuple[LocalMovement, ...]
    pending_transfers: tuple[dict[str, Any], ...]
    terminal_transfers: tuple[dict[str, Any], ...]
    unresolved: tuple[str, ...]
    source_sha256: str
    row_counts: dict[str, int]
    runtime_role: str


def _rows(response: Any, *, table: str) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        raise RuntimeError(f"PostgREST {table} response data is not an array")
    if not all(isinstance(row, dict) for row in data):
        raise RuntimeError(f"PostgREST {table} response contains a non-object row")
    return [cast(dict[str, Any], row) for row in data]


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class PostgrestReconciliationReader:
    """Read service-owned financial evidence through a service-role client.

    The reader paginates every table in a stable order and refuses repeated row
    identities.  Authorization itself is proven by the isolated real-stack test;
    this class never accepts a browser/anon client by configuration fallback.
    """

    def __init__(
        self,
        service_client: ServiceRoleClient,
        *,
        runtime_role: str,
        page_size: int = 500,
    ) -> None:
        if runtime_role != "service_role":
            raise ValueError("reconciliation reader requires the service_role runtime")
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self._client = service_client.client
        self._runtime_role = runtime_role
        self._page_size = page_size

    def _fetch_all(
        self,
        table: str,
        columns: str,
        *,
        order_by: str,
        filters: tuple[tuple[str, str, object], ...] = (),
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        start = 0
        while True:
            query = self._client.table(table).select(columns)
            for operation, column, value in filters:
                query = getattr(query, operation)(column, value)
            query = query.order(order_by).range(start, start + self._page_size - 1)
            page = _rows(query.execute(), table=table)
            for row in page:
                identity = _text(row.get(order_by))
                if identity is None:
                    raise RuntimeError(
                        f"PostgREST {table} row has no stable {order_by} identity"
                    )
                if identity in seen:
                    raise RuntimeError(
                        f"PostgREST {table} pagination repeated {order_by}={identity!r}"
                    )
                seen.add(identity)
                result.append(row)
            if len(page) < self._page_size:
                return result
            start += self._page_size

    @staticmethod
    def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for row in rows:
            identity = _text(row.get(key))
            if identity is None:
                raise RuntimeError(f"local evidence row is missing {key}")
            if identity in indexed:
                raise RuntimeError(f"duplicate local evidence identity {key}={identity!r}")
            indexed[identity] = row
        return indexed

    @staticmethod
    def _kind_for_payment(identity: dict[str, Any]) -> MovementKind:
        leg = _text(identity.get("leg"))
        if leg == "deposit":
            return MovementKind.SERVICE_DEPOSIT
        if leg == "balance":
            return MovementKind.SERVICE_BALANCE
        return MovementKind.COLLECTION

    def collect(self, *, report_date: date) -> LocalReconciliationEvidence:
        start = datetime.combine(report_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        day_filters = (
            ("gte", "created_at", start.isoformat()),
            ("lt", "created_at", end.isoformat()),
        )

        accounts = self._fetch_all(
            "ledger_accounts",
            "id,kind,vendor_id",
            order_by="id",
            filters=(("eq", "kind", "platform_cash"), ("is_", "vendor_id", "null")),
        )
        if len(accounts) != 1:
            raise RuntimeError(
                "expected exactly one unscoped platform_cash ledger account, "
                f"observed {len(accounts)}"
            )
        platform_cash_id = str(accounts[0]["id"])

        transactions = self._fetch_all(
            "ledger_transactions",
            "id,kind,checkout_group_id,order_id,payment_id,payout_id,refund_id,created_at",
            order_by="id",
            filters=day_filters,
        )
        postings = self._fetch_all(
            "ledger_postings",
            "id,transaction_id,account_id,amount_ngwee,created_at",
            order_by="id",
            filters=(
                ("eq", "account_id", platform_cash_id),
                *day_filters,
            ),
        )
        txn_by_id = self._index(transactions, "id")

        payment_ids = sorted(
            {
                value
                for row in transactions
                if (value := _text(row.get("payment_id"))) is not None
            }
        )
        payout_ids = sorted(
            {
                value
                for row in transactions
                if (value := _text(row.get("payout_id"))) is not None
            }
        )
        refund_ids = sorted(
            {
                value
                for row in transactions
                if (value := _text(row.get("refund_id"))) is not None
            }
        )

        payments = (
            self._fetch_all(
                "payments",
                "id,lenco_reference,rail,raw,status",
                order_by="id",
                filters=(("in_", "id", payment_ids),),
            )
            if payment_ids
            else []
        )
        receipts = (
            self._fetch_all(
                "payment_collection_receipts",
                "payment_id,receipt_identity,provider_reference,canonical_status_verified_at,accepted_at",
                order_by="payment_id",
                filters=(("in_", "payment_id", payment_ids),),
            )
            if payment_ids
            else []
        )
        exceptions = self._fetch_all(
            "payment_collection_exceptions",
            "id,payment_id,provider_reference,reason,first_observation,created_at",
            order_by="id",
            filters=day_filters,
        )
        exception_payment_ids = sorted(
            {
                value
                for row in exceptions
                if (value := _text(row.get("payment_id"))) is not None
            }
        )
        missing_exception_payment_ids = [
            value for value in exception_payment_ids if value not in payment_ids
        ]
        if missing_exception_payment_ids:
            payments.extend(
                self._fetch_all(
                    "payments",
                    "id,lenco_reference,rail,raw,status",
                    order_by="id",
                    filters=(("in_", "id", missing_exception_payment_ids),),
                )
            )
        # Include every unresolved transfer, even if it was created before this
        # day, plus transfers whose state changed during the day. They are
        # positions/status evidence, not paid money unless terminal evidence and
        # ledger linkage independently agree.
        active_payouts = self._fetch_all(
            "payouts",
            "id,amount_ngwee,rail,lenco_reference,status,resolve_snapshot,payout_kind,created_at,updated_at",
            order_by="id",
            filters=(("in_", "status", ["pending", "processing"]),),
        )
        changed_payouts = self._fetch_all(
            "payouts",
            "id,amount_ngwee,rail,lenco_reference,status,resolve_snapshot,payout_kind,created_at,updated_at",
            order_by="id",
            filters=(
                ("gte", "updated_at", start.isoformat()),
                ("lt", "updated_at", end.isoformat()),
            ),
        )
        payouts_by_identity = {str(row["id"]): row for row in active_payouts}
        for row in changed_payouts:
            payouts_by_identity[str(row["id"])] = row
        payouts = list(payouts_by_identity.values())
        refunds = self._fetch_all(
            "refunds",
            "id,order_id,amount_ngwee,status,payout_ref,breakdown,created_at,updated_at",
            order_by="id",
            filters=(
                ("gte", "updated_at", start.isoformat()),
                ("lt", "updated_at", end.isoformat()),
            ),
        )
        # A linked transfer/receipt may have been created before the report day.
        known_payout_ids = {_text(row.get("id")) for row in payouts}
        missing_payout_ids = [value for value in payout_ids if value not in known_payout_ids]
        if missing_payout_ids:
            payouts.extend(
                self._fetch_all(
                    "payouts",
                    "id,amount_ngwee,rail,lenco_reference,status,resolve_snapshot,payout_kind,created_at,updated_at",
                    order_by="id",
                    filters=(("in_", "id", missing_payout_ids),),
                )
            )
        known_refund_ids = {_text(row.get("id")) for row in refunds}
        missing_refund_ids = [value for value in refund_ids if value not in known_refund_ids]
        if missing_refund_ids:
            refunds.extend(
                self._fetch_all(
                    "refunds",
                    "id,order_id,amount_ngwee,status,payout_ref,breakdown,created_at,updated_at",
                    order_by="id",
                    filters=(("in_", "id", missing_refund_ids),),
                )
            )

        payments_by_id = self._index(payments, "id")
        receipts_by_payment = self._index(receipts, "payment_id")
        payouts_by_id = self._index(payouts, "id")
        refunds_by_id = self._index(refunds, "id")
        unresolved: list[str] = []
        movements: list[LocalMovement] = []

        for posting in postings:
            transaction_id = _text(posting.get("transaction_id"))
            if transaction_id is None or transaction_id not in txn_by_id:
                unresolved.append(
                    f"platform_cash posting {_text(posting.get('id'))!r} has no day transaction"
                )
                continue
            transaction = txn_by_id[transaction_id]
            payment_id = _text(transaction.get("payment_id"))
            payout_id = _text(transaction.get("payout_id"))
            refund_id = _text(transaction.get("refund_id"))
            order_id = _text(transaction.get("order_id"))
            checkout_id = _text(transaction.get("checkout_group_id"))
            amount = int(posting["amount_ngwee"])

            if payment_id is not None:
                payment = payments_by_id.get(payment_id, {})
                receipt = receipts_by_payment.get(payment_id, {})
                identity = _mapping(receipt.get("receipt_identity"))
                if not identity:
                    unresolved.append(f"payment {payment_id!r} has no accepted receipt identity")
                if payment.get("rail") == "card" and not receipt.get(
                    "canonical_status_verified_at"
                ):
                    unresolved.append(
                        f"card payment {payment_id!r} has no canonical verification timestamp"
                    )
                kind = self._kind_for_payment(identity) if identity else MovementKind.UNKNOWN
                movements.append(
                    LocalMovement(
                        local_id=str(posting["id"]),
                        movement_group=f"payment:{payment_id}",
                        kind=kind,
                        amount_ngwee=amount,
                        merchant_reference=_text(identity.get("merchant_reference")),
                        provider_reference=_text(identity.get("provider_reference")),
                        payment_id=payment_id,
                        checkout_id=checkout_id,
                        order_id=order_id or _text(identity.get("order_id")),
                        obligation_id=_text(identity.get("obligation_id")),
                        ledger_transaction_id=transaction_id,
                        ledger_linkage_id=payment_id,
                        allocation_id=order_id,
                        rail=_text(payment.get("rail")),
                        leg=_text(identity.get("leg")),
                    )
                )
                continue

            if payout_id is not None:
                payout = payouts_by_id.get(payout_id, {})
                snapshot = _mapping(payout.get("resolve_snapshot"))
                kind = (
                    MovementKind.REFUND_PAYOUT
                    if payout.get("payout_kind") == "customer_refund"
                    else MovementKind.VENDOR_PAYOUT
                )
                movements.append(
                    LocalMovement(
                        local_id=str(posting["id"]),
                        movement_group=f"payout:{payout_id}",
                        kind=kind,
                        amount_ngwee=amount,
                        merchant_reference=_text(payout.get("lenco_reference")),
                        provider_reference=_text(snapshot.get("provider_reference")),
                        payout_id=payout_id,
                        refund_id=refund_id,
                        order_id=order_id,
                        ledger_transaction_id=transaction_id,
                        ledger_linkage_id=payout_id,
                        rail=_text(payout.get("rail")),
                    )
                )
                continue

            if refund_id is not None:
                refund = refunds_by_id.get(refund_id, {})
                breakdown = _mapping(refund.get("breakdown"))
                movements.append(
                    LocalMovement(
                        local_id=str(posting["id"]),
                        movement_group=f"refund:{refund_id}",
                        kind=MovementKind.REFUND_PAYOUT,
                        amount_ngwee=amount,
                        merchant_reference=_text(breakdown.get("lenco_reference")),
                        refund_id=refund_id,
                        order_id=order_id or _text(refund.get("order_id")),
                        ledger_transaction_id=transaction_id,
                        ledger_linkage_id=refund_id,
                    )
                )
                continue

            movements.append(
                LocalMovement(
                    local_id=str(posting["id"]),
                    movement_group=f"unclassified:{transaction_id}",
                    kind=MovementKind.UNKNOWN,
                    amount_ngwee=amount,
                    checkout_id=checkout_id,
                    order_id=order_id,
                    ledger_transaction_id=transaction_id,
                )
            )
            unresolved.append(f"ledger transaction {transaction_id!r} has no provider linkage")

        for exception in exceptions:
            payment_id = _text(exception.get("payment_id"))
            payment = payments_by_id.get(payment_id or "", {})
            observation = _mapping(exception.get("first_observation"))
            raw_amount = observation.get("amount_ngwee")
            if payment_id is None or raw_amount is None:
                unresolved.append(
                    f"collection exception {_text(exception.get('id'))!r} lacks identity or amount"
                )
                continue
            movements.append(
                LocalMovement(
                    local_id=str(exception["id"]),
                    movement_group=f"collection-exception:{exception['id']}",
                    kind=MovementKind.COLLECTION_EXCEPTION,
                    amount_ngwee=int(raw_amount),
                    merchant_reference=_text(payment.get("lenco_reference")),
                    provider_reference=_text(exception.get("provider_reference")),
                    payment_id=payment_id,
                    collection_exception_id=str(exception["id"]),
                    rail=_text(payment.get("rail")),
                )
            )

        transfer_rows = []
        for payout in sorted(payouts, key=lambda row: str(row.get("id", ""))):
            snapshot = _mapping(payout.get("resolve_snapshot"))
            transfer_rows.append(
                {
                    "payout_id": str(payout["id"]),
                    "payout_kind": payout.get("payout_kind"),
                    "status": payout.get("status"),
                    "merchant_reference": payout.get("lenco_reference"),
                    "provider_reference": snapshot.get("provider_reference"),
                    "provider_status": snapshot.get("transfer_status"),
                }
            )
        pending = tuple(
            row for row in transfer_rows if row["status"] in {"pending", "processing"}
        )
        terminal = tuple(
            row for row in transfer_rows if row["status"] in {"paid", "failed"}
        )

        source_rows = {
            "accounts": accounts,
            "transactions": transactions,
            "postings": postings,
            "payments": payments,
            "receipts": receipts,
            "exceptions": exceptions,
            "payouts": payouts,
            "refunds": refunds,
        }
        return LocalReconciliationEvidence(
            movements=tuple(sorted(movements, key=lambda row: row.local_id)),
            pending_transfers=pending,
            terminal_transfers=terminal,
            unresolved=tuple(sorted(set(unresolved))),
            source_sha256=_canonical_hash(source_rows),
            row_counts={key: len(rows) for key, rows in source_rows.items()},
            runtime_role=self._runtime_role,
        )
