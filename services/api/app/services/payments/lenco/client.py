"""Async Lenco HTTP client and PaymentStrategy adapter."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
from typing import Any, cast

import httpx
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionRequest,
    InitiateCollectionResult,
    InitiatePayoutRequest,
    InitiatePayoutResult,
    PaymentProviderError,
    ProviderErrorKind,
    ProviderOutcome,
    ProviderResult,
    QueryStatusRequest,
    QueryStatusResult,
    ResolveAccountRequest,
    ResolveAccountResult,
    TransferStatus,
    VerifyWebhookRequest,
    VerifyWebhookResult,
)
from app.services.payments.gate import PaymentsDisabledError, payments_enabled
from app.services.payments.lenco.config import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_IDEMPOTENT_RETRIES,
    RETRY_BACKOFF_BASE_SECONDS,
    get_api_token,
    get_base_url,
    zamtel_collections_enabled,
)
from app.services.payments.lenco.models import (
    LencoBankPayoutRequest,
    LencoClientError,
    LencoCollectionRequest,
    LencoCollectionResponse,
    LencoCollectionStatusResponse,
    LencoErrorCategory,
    LencoMomoPayoutRequest,
    LencoResolveBankAccountRequest,
    LencoResolveBankAccountResponse,
    LencoResolveMobileMoneyRequest,
    LencoResolveMobileMoneyResponse,
    LencoTransferResponse,
    LencoTransferStatusResponse,
    lenco_failure,
    raise_lenco_failure,
)
from app.services.payments.money import ngwee_to_major_str

logger = logging.getLogger(__name__)

_COLLECTION_OPERATORS = frozenset({"mtn", "airtel"})
_PAYOUT_OPERATORS = frozenset({"mtn", "airtel", "zamtel"})
_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _snake_key(key: str) -> str:
    return _CAMEL_RE.sub("_", key).lower()


def _camel_to_snake(value: Any) -> Any:
    if isinstance(value, dict):
        return {_snake_key(str(key)): _camel_to_snake(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camel_to_snake(item) for item in value]
    return value


def _amount_json_value(amount_major: str) -> str:
    """Embed a validated 2dp major-unit string as a JSON numeric literal."""
    return amount_major


def _build_json_body(payload: dict[str, Any]) -> str:
    """Serialize a payload, embedding amount as a JSON number without float math."""
    if "amount" in payload:
        amount = payload["amount"]
        if not isinstance(amount, str):
            msg = "amount must be a decimal-major string"
            raise TypeError(msg)
        remaining = {key: value for key, value in payload.items() if key != "amount"}
        inner = json.dumps(remaining, separators=(",", ":"), ensure_ascii=True)
        if inner == "{}":
            return f'{{"amount":{_amount_json_value(amount)}}}'
        return "{" + f'"amount":{_amount_json_value(amount)},' + inner[1:]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _map_collection_status(status: str) -> CollectionStatus:
    try:
        return CollectionStatus(status)
    except ValueError:
        return CollectionStatus.PENDING


def _map_transfer_status(status: str) -> TransferStatus:
    try:
        return TransferStatus(status)
    except ValueError:
        return TransferStatus.PENDING


def _map_provider_outcome(status: str) -> ProviderOutcome:
    if status == "successful":
        return ProviderOutcome.SUCCESSFUL
    if status == "failed":
        return ProviderOutcome.FAILED
    return ProviderOutcome.PENDING


def _validate_collection_operator(operator: str) -> str:
    normalized = operator.strip().lower()
    if normalized in _COLLECTION_OPERATORS:
        return normalized
    if normalized == "zamtel" and zamtel_collections_enabled():
        return normalized
    if normalized == "zamtel":
        raise LencoClientError(
            LencoErrorCategory.PROVIDER_ERROR,
            "Zamtel collections are disabled pending F9a confirmation",
        )
    raise LencoClientError(
        LencoErrorCategory.PROVIDER_ERROR,
        f"unsupported collection operator: {operator}",
    )


def _validate_payout_operator(operator: str) -> str:
    normalized = operator.strip().lower()
    if normalized in _PAYOUT_OPERATORS:
        return normalized
    raise LencoClientError(
        LencoErrorCategory.PROVIDER_ERROR,
        f"unsupported payout operator: {operator}",
    )


def _envelope_error_code(envelope: dict[str, Any]) -> str | None:
    raw = envelope.get("errorCode")
    return str(raw) if raw else None


class LencoClient:
    """Low-level async HTTP client for the Lenco REST API."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._token = token
        self._base_url = base_url
        self._timeout = timeout
        self._http = http_client
        self._owns_http = http_client is None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url or get_base_url(),
                timeout=self._timeout,
            )
        return self._http

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    def _token_value(self) -> str:
        return self._token if self._token is not None else get_api_token()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        allow_retry: bool = False,
        authoritative_not_found: bool = False,
        reference: str | None = None,
        dispatch_may_have_succeeded: bool = False,
    ) -> dict[str, Any]:
        client = await self._client()
        headers = _auth_headers(self._token_value())
        content = _build_json_body(json_body) if json_body is not None else None
        attempts = MAX_IDEMPOTENT_RETRIES if allow_retry else 1

        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                response = await client.request(method, path, headers=headers, content=content)
            except httpx.TimeoutException as exc:
                last_exc = exc
                if allow_retry and attempt < attempts - 1:
                    await asyncio.sleep(RETRY_BACKOFF_BASE_SECONDS * (2**attempt))
                    continue
                raise lenco_failure(
                    message="request timed out",
                    timed_out=True,
                    reference=reference,
                    observation_uncertain=True,
                    dispatch_may_have_succeeded=dispatch_may_have_succeeded,
                ) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if allow_retry and attempt < attempts - 1:
                    await asyncio.sleep(RETRY_BACKOFF_BASE_SECONDS * (2**attempt))
                    continue
                raise lenco_failure(
                    message=str(exc),
                    kind=ProviderErrorKind.TRANSPORT,
                    reference=reference,
                    observation_uncertain=True,
                    dispatch_may_have_succeeded=dispatch_may_have_succeeded,
                ) from exc

            try:
                body = response.json()
            except ValueError as exc:
                raise lenco_failure(
                    message="invalid JSON response",
                    http_status=response.status_code,
                    kind=ProviderErrorKind.INVALID_OBSERVATION,
                    reference=reference,
                    observation_uncertain=True,
                    dispatch_may_have_succeeded=dispatch_may_have_succeeded,
                ) from exc

            if not isinstance(body, dict):
                raise_lenco_failure(
                    message="unexpected response envelope",
                    kind=ProviderErrorKind.INVALID_OBSERVATION,
                    reference=reference,
                    observation_uncertain=True,
                    dispatch_may_have_succeeded=dispatch_may_have_succeeded,
                )

            envelope = cast(dict[str, Any], body)

            if response.status_code >= 500:
                if allow_retry and attempt < attempts - 1:
                    await asyncio.sleep(RETRY_BACKOFF_BASE_SECONDS * (2**attempt))
                    continue
                raise_lenco_failure(
                    error_code=_envelope_error_code(envelope),
                    message=str(envelope.get("message", "server error")),
                    http_status=response.status_code,
                    reference=reference,
                    observation_uncertain=True,
                    dispatch_may_have_succeeded=dispatch_may_have_succeeded,
                )

            if response.status_code >= 400:
                if authoritative_not_found and _envelope_error_code(envelope) == "11":
                    return envelope
                raise_lenco_failure(
                    error_code=_envelope_error_code(envelope),
                    message=str(envelope.get("message", "client error")),
                    http_status=response.status_code,
                    reference=reference,
                    observation_uncertain=True,
                    dispatch_may_have_succeeded=dispatch_may_have_succeeded,
                )

            if envelope.get("status") is False:
                if authoritative_not_found and _envelope_error_code(envelope) == "11":
                    return envelope
                raise_lenco_failure(
                    error_code=_envelope_error_code(envelope),
                    message=str(envelope.get("message", "request failed")),
                    reference=reference,
                    observation_uncertain=True,
                    dispatch_may_have_succeeded=dispatch_may_have_succeeded,
                )

            return envelope

        if last_exc is not None:
            raise last_exc
        raise_lenco_failure(message="request failed after retries")

    async def initiate_collection(self, request: LencoCollectionRequest) -> LencoCollectionResponse:
        operator = _validate_collection_operator(request.operator)
        payload = {
            "amount": request.amount_major,
            "reference": request.reference,
            "phone": request.phone,
            "operator": operator,
            "country": request.country,
            "bearer": request.bearer,
        }
        body = await self._request(
            "POST",
            "/collections/mobile-money",
            json_body=payload,
            reference=request.reference,
            dispatch_may_have_succeeded=True,
        )
        return LencoCollectionResponse.model_validate(_camel_to_snake(body))

    async def query_collection_status(self, reference: str) -> ProviderResult:
        body = await self._request(
            "GET",
            f"/collections/status/{reference}",
            allow_retry=True,
            authoritative_not_found=True,
            reference=reference,
        )
        try:
            response = LencoCollectionStatusResponse.model_validate(_camel_to_snake(body))
        except ValueError as exc:
            raise lenco_failure(
                message="invalid collection status observation",
                kind=ProviderErrorKind.INVALID_OBSERVATION,
                reference=reference,
                observation_uncertain=True,
            ) from exc
        if response.error_code == "11" and response.data is None:
            return ProviderResult(
                requested_reference=reference,
                outcome=ProviderOutcome.NOT_FOUND,
                raw=response.model_dump(),
            )
        if response.data is None:
            raise lenco_failure(
                message="collection status response missing data",
                kind=ProviderErrorKind.INVALID_OBSERVATION,
                reference=reference,
                observation_uncertain=True,
            )
        data = response.data
        return ProviderResult(
            requested_reference=reference,
            outcome=_map_provider_outcome(data.status),
            reference=data.reference,
            status=data.status,
            amount_major=data.amount,
            currency=data.currency,
            provider_reference=data.lenco_reference,
            failure_reason=data.reason_for_failure,
            raw=response.model_dump(),
        )

    async def resolve_mobile_money(
        self,
        request: LencoResolveMobileMoneyRequest,
    ) -> LencoResolveMobileMoneyResponse:
        operator = _validate_payout_operator(request.operator)
        payload = {
            "phone": request.phone,
            "operator": operator,
            "country": request.country,
        }
        body = await self._request(
            "POST",
            "/resolve/mobile-money",
            json_body=payload,
            allow_retry=True,
        )
        return LencoResolveMobileMoneyResponse.model_validate(_camel_to_snake(body))

    async def resolve_bank_account(
        self,
        request: LencoResolveBankAccountRequest,
    ) -> LencoResolveBankAccountResponse:
        payload = {
            "accountNumber": request.account_number,
            "bankId": request.bank_id,
            "country": request.country,
        }
        body = await self._request(
            "POST",
            "/resolve/bank-account",
            json_body=payload,
            allow_retry=True,
        )
        return LencoResolveBankAccountResponse.model_validate(_camel_to_snake(body))

    async def initiate_momo_payout(self, request: LencoMomoPayoutRequest) -> LencoTransferResponse:
        operator = _validate_payout_operator(request.operator)
        amount_major = ngwee_to_major_str(request.amount_ngwee, currency=request.currency)
        payload: dict[str, Any] = {
            "accountId": request.account_id,
            "amount": amount_major,
            "reference": request.reference,
            "phone": request.phone,
            "operator": operator,
            "country": request.country,
        }
        if request.narration is not None:
            payload["narration"] = request.narration
        if request.transfer_recipient_id is not None:
            payload["transferRecipientId"] = request.transfer_recipient_id
        body = await self._request(
            "POST",
            "/transfers/mobile-money",
            json_body=payload,
            reference=request.reference,
            dispatch_may_have_succeeded=True,
        )
        return LencoTransferResponse.model_validate(_camel_to_snake(body))

    async def initiate_bank_payout(self, request: LencoBankPayoutRequest) -> LencoTransferResponse:
        amount_major = ngwee_to_major_str(request.amount_ngwee, currency=request.currency)
        payload: dict[str, Any] = {
            "accountId": request.account_id,
            "amount": amount_major,
            "reference": request.reference,
            "accountNumber": request.account_number,
            "bankId": request.bank_id,
            "country": request.country,
        }
        if request.narration is not None:
            payload["narration"] = request.narration
        if request.transfer_recipient_id is not None:
            payload["transferRecipientId"] = request.transfer_recipient_id
        body = await self._request(
            "POST",
            "/transfers/bank-account",
            json_body=payload,
            reference=request.reference,
            dispatch_may_have_succeeded=True,
        )
        return LencoTransferResponse.model_validate(_camel_to_snake(body))

    async def query_transfer_status(self, reference: str) -> ProviderResult:
        body = await self._request(
            "GET",
            f"/transfers/status/{reference}",
            allow_retry=True,
            authoritative_not_found=True,
            reference=reference,
        )
        try:
            response = LencoTransferStatusResponse.model_validate(_camel_to_snake(body))
        except ValueError as exc:
            raise lenco_failure(
                message="invalid transfer status observation",
                kind=ProviderErrorKind.INVALID_OBSERVATION,
                reference=reference,
                observation_uncertain=True,
            ) from exc
        if response.error_code == "11" and response.data is None:
            return ProviderResult(
                requested_reference=reference,
                outcome=ProviderOutcome.NOT_FOUND,
                raw=response.model_dump(),
            )
        if response.data is None:
            raise lenco_failure(
                message="transfer status response missing data",
                kind=ProviderErrorKind.INVALID_OBSERVATION,
                reference=reference,
                observation_uncertain=True,
            )
        data = response.data
        return ProviderResult(
            requested_reference=reference,
            outcome=ProviderOutcome(data.status),
            reference=data.reference,
            status=data.status,
            amount_major=data.amount,
            currency=data.currency,
            provider_reference=data.lenco_reference,
            debit_account_id=data.account_id,
            destination=data.credit_account,
            failure_reason=data.reason_for_failure,
            raw=response.model_dump(),
        )

    def verify_webhook_signature(
        self,
        *,
        raw_body: bytes,
        signature: str,
        token: str | None = None,
    ) -> bool:
        api_token = token if token is not None else self._token_value()
        signing_key = hashlib.sha256(api_token.encode("utf-8")).hexdigest().encode("utf-8")
        expected = hmac.new(signing_key, raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature.strip().lower())


class LencoStrategy:
    """Lenco implementation of the provider-agnostic PaymentStrategy seam."""

    def __init__(self, client: LencoClient | None = None) -> None:
        self._client = client or LencoClient()

    async def initiate_collection(
        self,
        request: InitiateCollectionRequest,
    ) -> InitiateCollectionResult:
        # Defence-in-depth backstop: the API-boundary guards (initiate.py /
        # payment_status.py) normally block first, but no code path may reach the
        # Lenco network while payments are disabled.
        if not payments_enabled():
            raise PaymentsDisabledError()
        operator = _validate_collection_operator(request.operator)
        amount_major = ngwee_to_major_str(request.amount_ngwee, currency=request.currency)
        lenco_request = LencoCollectionRequest(
            amount_major=amount_major,
            reference=request.reference,
            phone=request.phone,
            operator=operator,  # type: ignore[arg-type]
            country=request.country,
            bearer=request.bearer,
        )
        try:
            response = await self._client.initiate_collection(lenco_request)
        except LencoClientError:
            raise
        except Exception as exc:
            raise PaymentProviderError("provider_error", str(exc)) from exc

        if response.data is None:
            raise PaymentProviderError("provider_error", "collection response missing data")

        data = response.data
        return InitiateCollectionResult(
            provider_reference=data.lenco_reference,
            status=_map_collection_status(data.status),
            amount_major=data.amount,
            currency=data.currency,
            raw=response.model_dump(),
        )

    async def query_status(self, request: QueryStatusRequest) -> QueryStatusResult:
        try:
            result = await self._client.query_collection_status(request.reference)
        except LencoClientError:
            raise
        except Exception as exc:
            raise PaymentProviderError("provider_error", str(exc)) from exc

        return result

    async def initiate_payout(self, request: InitiatePayoutRequest) -> InitiatePayoutResult:
        raise PaymentProviderError(
            "provider_error",
            "InitiatePayoutRequest lacks payout rail fields; "
            "use initiate_momo_payout or initiate_bank_payout on LencoStrategy",
        )

    async def initiate_momo_payout(self, request: LencoMomoPayoutRequest) -> InitiatePayoutResult:
        try:
            response = await self._client.initiate_momo_payout(request)
        except LencoClientError:
            raise
        except Exception as exc:
            raise PaymentProviderError("provider_error", str(exc)) from exc

        if response.data is None:
            raise PaymentProviderError("provider_error", "payout response missing data")

        data = response.data
        return InitiatePayoutResult(
            reference=data.reference,
            provider_reference=data.lenco_reference,
            status=_map_transfer_status(data.status),
            amount_major=data.amount,
            currency=data.currency,
            debit_account_id=data.account_id,
            destination=data.credit_account,
            failure_reason=data.reason_for_failure,
            raw=response.model_dump(),
        )

    async def initiate_bank_payout(self, request: LencoBankPayoutRequest) -> InitiatePayoutResult:
        try:
            response = await self._client.initiate_bank_payout(request)
        except LencoClientError:
            raise
        except Exception as exc:
            raise PaymentProviderError("provider_error", str(exc)) from exc

        if response.data is None:
            raise PaymentProviderError("provider_error", "payout response missing data")

        data = response.data
        return InitiatePayoutResult(
            reference=data.reference,
            provider_reference=data.lenco_reference,
            status=_map_transfer_status(data.status),
            amount_major=data.amount,
            currency=data.currency,
            debit_account_id=data.account_id,
            destination=data.credit_account,
            failure_reason=data.reason_for_failure,
            raw=response.model_dump(),
        )

    async def resolve_account(self, request: ResolveAccountRequest) -> ResolveAccountResult:
        lenco_request = LencoResolveMobileMoneyRequest(
            phone=request.phone,
            operator=_validate_payout_operator(request.operator),  # type: ignore[arg-type]
            country=request.country,
        )
        try:
            response = await self._client.resolve_mobile_money(lenco_request)
        except LencoClientError:
            raise
        except Exception as exc:
            raise PaymentProviderError("provider_error", str(exc)) from exc

        if response.data is None:
            raise PaymentProviderError("provider_error", "resolve response missing data")

        return ResolveAccountResult(
            account_name=response.data.account_name,
            raw=response.model_dump(),
        )

    async def verify_webhook(self, request: VerifyWebhookRequest) -> VerifyWebhookResult:
        valid = self._client.verify_webhook_signature(
            raw_body=request.raw_body,
            signature=request.signature,
        )
        event_id: str | None = None
        if valid:
            try:
                payload = json.loads(request.raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict) and isinstance(data.get("id"), str):
                    event_id = data["id"]
        return VerifyWebhookResult(valid=valid, event_id=event_id)
