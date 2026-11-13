"""Read-only Lenco account and transaction evidence for daily reconciliation.

Only fields documented in ``docs/ops/lenco/lenco-api-distilled.md`` are
accepted.  Missing provider data is never backfilled from a local obligation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import httpx
from app.services.payments.lenco.config import (
    LencoEnvironment,
    get_api_token,
    get_base_url,
    get_lenco_environment,
)
from app.services.payments.money import major_str_to_ngwee
from app.services.payments.reconciliation_matcher import (
    AccountSnapshot,
    EvidenceOrigin,
    MovementDirection,
    MovementKind,
    ProviderMovement,
    ProviderPage,
    select_configured_account,
)

_LENCO_REFERENCE = re.compile(r"\s/\s*([-._A-Za-z0-9]+)\s*$")
_MAX_PAGES = 1_000
_NGWEE_PER_MAJOR = Decimal(100)
_TWO_PLACES = Decimal("0.01")


class LencoReconciliationError(RuntimeError):
    """The provider transport or documented observation was unusable."""


@dataclass(frozen=True, slots=True)
class LencoReconciliationEvidence:
    account: AccountSnapshot
    pages: tuple[ProviderPage, ...]
    account_response_sha256: str
    observed_at: datetime
    query_from: date
    query_to: date

    @property
    def transaction_response_sha256s(self) -> tuple[str, ...]:
        return tuple(page.raw_sha256 or "" for page in self.pages)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")
    return value.strip()


def _required_nonnegative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be nonnegative")
    return parsed


def _signed_major_str_to_ngwee(value: object, *, field_name: str) -> int:
    raw = _required_text(value, field_name=field_name)
    try:
        major = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal-major string") from exc
    if not major.is_finite() or major != major.quantize(_TWO_PLACES):
        raise ValueError(f"{field_name} must be finite with at most two decimal places")
    return int((major * _NGWEE_PER_MAJOR).to_integral_exact())


def _provider_timestamp(value: object) -> datetime:
    raw = _required_text(value, field_name="transaction.datetime")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("transaction.datetime must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("transaction.datetime must include a timezone")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("transaction.datetime must be UTC")
    return parsed.astimezone(UTC)


def _reference_from_documented_narration(narration: str) -> str | None:
    match = _LENCO_REFERENCE.search(narration)
    return match.group(1) if match else None


class LencoReconciliationAdapter:
    """Collect the configured account and every declared transaction page."""

    def __init__(
        self,
        *,
        configured_account_id: str,
        currency: str = "ZMW",
        http_client: httpx.AsyncClient | None = None,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        trust_env: bool = True,
        evidence_origin: EvidenceOrigin | None = None,
    ) -> None:
        if not configured_account_id.strip():
            raise ValueError("configured account id is required")
        self._configured_account_id = configured_account_id.strip()
        self._currency = currency
        self._token = token
        self._base_url = base_url
        self._timeout = timeout
        self._trust_env = trust_env
        if evidence_origin is None:
            evidence_origin = (
                EvidenceOrigin.SANDBOX_PROVIDER
                if get_lenco_environment() == LencoEnvironment.SANDBOX
                else EvidenceOrigin.PRODUCTION_PROVIDER
            )
        self._evidence_origin = evidence_origin
        self._http = http_client
        self._owns_http = http_client is None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url or get_base_url(),
                timeout=self._timeout,
                trust_env=self._trust_env,
            )
        return self._http

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    def _token_value(self) -> str:
        return self._token if self._token is not None else get_api_token()

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        client = await self._client()
        try:
            response = await client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {self._token_value()}"},
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LencoReconciliationError(f"Lenco GET {path} failed: {exc}") from exc
        if not isinstance(body, dict):
            raise LencoReconciliationError(f"Lenco GET {path} returned a non-object envelope")
        envelope = cast(dict[str, Any], body)
        if envelope.get("status") is not True:
            message = envelope.get("message")
            raise LencoReconciliationError(
                f"Lenco GET {path} was not successful: {message!s}"
            )
        return envelope

    @staticmethod
    def _parse_account(item: object) -> AccountSnapshot:
        if not isinstance(item, dict):
            raise ValueError("account row must be an object")
        row = cast(dict[str, Any], item)
        return AccountSnapshot(
            account_id=_required_text(row.get("id"), field_name="account.id"),
            currency=_required_text(row.get("currency"), field_name="account.currency"),
            available_balance_ngwee=_signed_major_str_to_ngwee(
                row.get("availableBalance"),
                field_name="account.availableBalance",
            ),
            ledger_balance_ngwee=_signed_major_str_to_ngwee(
                row.get("ledgerBalance"),
                field_name="account.ledgerBalance",
            ),
        )

    def _parse_movement(self, item: object) -> ProviderMovement:
        if not isinstance(item, dict):
            raise ValueError("transaction row must be an object")
        row = cast(dict[str, Any], item)
        txn_type = _required_text(row.get("type"), field_name="transaction.type").lower()
        if txn_type == "credit":
            direction = MovementDirection.CREDIT
        elif txn_type == "debit":
            direction = MovementDirection.DEBIT
        else:
            raise ValueError(f"transaction.type is unsupported: {txn_type!r}")
        narration = _required_text(row.get("narration"), field_name="transaction.narration")
        provider_reference = _reference_from_documented_narration(narration)
        return ProviderMovement(
            movement_id=_required_text(row.get("id"), field_name="transaction.id"),
            account_id=_required_text(
                row.get("accountId"), field_name="transaction.accountId"
            ),
            currency=_required_text(
                row.get("currency"), field_name="transaction.currency"
            ),
            amount_ngwee=abs(
                major_str_to_ngwee(
                    _required_text(row.get("amount"), field_name="transaction.amount")
                )
            ),
            direction=direction,
            # The transaction feed documents debit/credit, not a Convergeo
            # business kind.  Kind classification therefore remains unresolved.
            kind=MovementKind.UNKNOWN,
            observed_at=_provider_timestamp(row.get("datetime")),
            merchant_reference=None,
            provider_reference=provider_reference,
            provider_reference_source=(
                "transaction.narration" if provider_reference is not None else None
            ),
            running_balance_ngwee=_signed_major_str_to_ngwee(
                row.get("balance"), field_name="transaction.balance"
            ),
            evidence_origin=self._evidence_origin,
        )

    @staticmethod
    def _parse_meta(envelope: dict[str, Any]) -> tuple[int, int, int, int]:
        meta = envelope.get("meta")
        if not isinstance(meta, dict):
            raise ValueError("transaction envelope is missing meta")
        typed = cast(dict[str, Any], meta)
        current = _required_nonnegative_int(
            typed.get("currentPage"), field_name="meta.currentPage"
        )
        page_count = _required_nonnegative_int(
            typed.get("pageCount"), field_name="meta.pageCount"
        )
        per_page = _required_nonnegative_int(
            typed.get("perPage"), field_name="meta.perPage"
        )
        total = _required_nonnegative_int(typed.get("total"), field_name="meta.total")
        if current < 1 or page_count < 1 or per_page < 1:
            raise ValueError("transaction pagination values must be positive")
        if current > page_count:
            raise ValueError("meta.currentPage exceeds meta.pageCount")
        return current, page_count, per_page, total

    async def collect(self, *, report_date: date) -> LencoReconciliationEvidence:
        observed_at = datetime.now(UTC)
        accounts_envelope = await self._get("/accounts")
        account_data = accounts_envelope.get("data")
        if not isinstance(account_data, list):
            raise LencoReconciliationError("Lenco accounts response data is not an array")
        try:
            accounts = tuple(self._parse_account(item) for item in account_data)
            account = select_configured_account(
                accounts,
                configured_account_id=self._configured_account_id,
                currency=self._currency,
            )
        except ValueError as exc:
            raise LencoReconciliationError(str(exc)) from exc

        start = datetime.combine(report_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        base_params = {
            "accountId": account.account_id,
            "from": start.date().isoformat(),
            "to": (end - timedelta(microseconds=1)).date().isoformat(),
        }
        pages: list[ProviderPage] = []
        requested_page = 1
        declared_page_count: int | None = None
        while requested_page <= (declared_page_count or 1):
            envelope = await self._get(
                "/transactions",
                params={**base_params, "page": str(requested_page)},
            )
            raw_hash = _canonical_sha256(envelope)
            data = envelope.get("data")
            errors: list[str] = []
            movements: list[ProviderMovement] = []
            if not isinstance(data, list):
                errors.append("transaction envelope data is not an array")
            else:
                for index, item in enumerate(data):
                    try:
                        movements.append(self._parse_movement(item))
                    except ValueError as exc:
                        errors.append(f"transaction row {index} invalid: {exc}")

            current_page: int | None = None
            page_count: int | None = None
            total: int | None = None
            try:
                current_page, page_count, _per_page, total = self._parse_meta(envelope)
            except ValueError as exc:
                errors.append(str(exc))
            if current_page is not None and current_page != requested_page:
                errors.append(
                    f"requested page {requested_page}, provider returned page {current_page}"
                )
            pages.append(
                ProviderPage(
                    page_number=current_page or requested_page,
                    cursor=None,
                    next_cursor=None,
                    page_count=page_count,
                    total=total,
                    movements=tuple(movements),
                    error="; ".join(errors) if errors else None,
                    raw_sha256=raw_hash,
                )
            )
            if page_count is None:
                break
            if page_count > _MAX_PAGES:
                raise LencoReconciliationError(
                    f"provider declared {page_count} transaction pages; limit is {_MAX_PAGES}"
                )
            declared_page_count = page_count
            requested_page += 1

        return LencoReconciliationEvidence(
            account=account,
            pages=tuple(pages),
            account_response_sha256=_canonical_sha256(accounts_envelope),
            observed_at=observed_at,
            query_from=start.date(),
            query_to=(end - timedelta(microseconds=1)).date(),
        )
