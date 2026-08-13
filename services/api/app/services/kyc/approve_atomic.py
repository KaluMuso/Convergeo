"""Atomic KYC approval via Postgres RPC (approve_kyc_vendor)."""

from __future__ import annotations

from typing import Any, Protocol, cast

from app.errors import AppError
from postgrest.exceptions import APIError

_RPC_NAME = "approve_kyc_vendor"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _map_rpc_error(exc: APIError) -> AppError:
    message = str(getattr(exc, "message", "") or "")
    details_msg = ""
    if isinstance(exc.args[0], dict):
        details_msg = str(exc.args[0].get("message") or "")
    hint = details_msg or message
    code = "internal_error"
    http_status = 500

    if "not_found:kyc_record" in hint or "KYC record not found" in hint:
        code = "not_found"
        http_status = 404
    elif "not_found:vendor" in hint or "Vendor not found" in hint:
        code = "not_found"
        http_status = 404
    elif "kyc_invalid_transition" in hint or "Cannot transition from" in hint:
        code = "kyc_invalid_transition"
        http_status = 409
    elif "kyc_transition_conflict" in hint or "Concurrent transition" in hint:
        code = "kyc_transition_conflict"
        http_status = 409
    elif "kyc_name_match_required" in hint or "MoMo name-match" in hint:
        code = "kyc_name_match_required"
        http_status = 409
    elif "validation_error:tier_mismatch" in hint or "tier must match" in hint.lower():
        code = "validation_error"
        http_status = 422
    elif "validation_error:tier" in hint:
        code = "validation_error"
        http_status = 422
    elif "vendor_role_missing_owner" in hint:
        code = "vendor_role_missing_owner"
        http_status = 500
    elif "vendor_role_grant_failed" in hint:
        code = "vendor_role_grant_failed"
        http_status = 500
    elif getattr(exc, "code", None) == "42501":
        code = "forbidden"
        http_status = 403

    return AppError(
        code=code,
        message=hint or "KYC approval failed",
        http_status=http_status,
    )


def approve_kyc_vendor_atomic(
    service_client: ServiceRoleClient,
    *,
    actor_id: str,
    kyc_record_id: str,
    tier: int,
    reviewer_notes: str | None = None,
) -> dict[str, Any]:
    """Run the approve_kyc_vendor RPC and return the after-state payload."""
    params: dict[str, Any] = {
        "p_actor_id": actor_id,
        "p_kyc_record_id": kyc_record_id,
        "p_tier": tier,
        "p_reviewer_notes": reviewer_notes,
    }
    try:
        response = service_client.client.rpc(_RPC_NAME, params).execute()
    except APIError as exc:
        raise _map_rpc_error(exc) from exc

    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return cast(dict[str, Any], data[0])
    raise AppError(
        code="internal_error",
        message="approve_kyc_vendor returned no payload",
        http_status=500,
    )
