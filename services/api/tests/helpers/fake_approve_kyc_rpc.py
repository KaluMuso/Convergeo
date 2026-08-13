"""In-memory fake for public.approve_kyc_vendor RPC used by API unit tests."""

from __future__ import annotations

from typing import Any, Protocol, cast

from app.errors import AppError


class _TableStore(Protocol):
    def table(self, name: str) -> Any: ...


def _store_rows(client: _TableStore, table: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], client.table(table).rows)


def _upsert_vendor_role(store: dict[str, Any], owner: str) -> str:
    if store.get("_block_vendor_role_grant"):
        raise AppError(
            code="vendor_role_grant_failed",
            message="forced role grant failure",
            http_status=500,
        )
    roles = store.setdefault("user_roles", [])
    for row in roles:
        if str(row["user_id"]) == owner and row["role"] == "vendor":
            return "already_present"
    roles.append({"user_id": owner, "role": "vendor"})
    return "granted"


def fake_approve_kyc_vendor(
    client: _TableStore,
    params: dict[str, Any],
) -> dict[str, Any]:
    kyc_rows = _store_rows(client, "kyc_records")
    vendor_rows = _store_rows(client, "vendors")
    audit_rows = _store_rows(client, "audit_log")

    kyc_id = str(params["p_kyc_record_id"])
    tier = int(params["p_tier"])
    actor_id = str(params["p_actor_id"])
    notes = params.get("p_reviewer_notes")

    kyc_matches = [row for row in kyc_rows if str(row["id"]) == kyc_id]
    if not kyc_matches:
        raise AppError(code="not_found", message="KYC record not found", http_status=404)
    kyc = kyc_matches[0]
    vendor_matches = [row for row in vendor_rows if str(row["id"]) == str(kyc["vendor_id"])]
    if not vendor_matches:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    vendor = vendor_matches[0]
    owner = str(vendor["owner_user_id"])
    if not owner:
        raise AppError(
            code="vendor_role_missing_owner",
            message="Vendor has no owner_user_id",
            http_status=500,
        )

    momo = kyc.get("momo_name_match") or {}
    if momo.get("matched") is False:
        raise AppError(
            code="kyc_name_match_required",
            message="KYC cannot be approved while MoMo name-match is flagged",
            http_status=409,
        )
    if tier != int(kyc["tier"]):
        raise AppError(
            code="validation_error",
            message="Approval tier must match the KYC record tier",
            http_status=422,
        )

    status = str(kyc["status"])
    normalized = "submitted" if status == "pending" else status
    before_vendor = {
        "id": vendor["id"],
        "status": vendor["status"],
        "kyc_tier": vendor.get("kyc_tier"),
    }
    before_kyc = {
        "id": kyc["id"],
        "status": normalized,
        "tier": kyc["tier"],
        "reviewed_by": kyc.get("reviewed_by"),
        "reviewed_at": kyc.get("reviewed_at"),
        "decision_reason": kyc.get("decision_reason"),
        "lifecycle_reason": kyc.get("lifecycle_reason"),
    }

    if normalized == "approved" and vendor["status"] == "active":
        role_outcome = _upsert_vendor_role(
            {"user_roles": _store_rows(client, "user_roles")}, owner
        )
        return {
            "vendor": before_vendor,
            "kyc_record": before_kyc,
            "vendor_role": {
                "user_id": owner,
                "role": "vendor",
                "outcome": role_outcome,
                "vendor_id": vendor["id"],
            },
        }

    if normalized not in {"submitted", "under_review"}:
        raise AppError(
            code="kyc_invalid_transition",
            message=f"Cannot transition from {normalized} to approved",
            http_status=409,
        )

    role_store: dict[str, Any] = {
        "user_roles": _store_rows(client, "user_roles"),
        "_block_vendor_role_grant": getattr(client, "_block_vendor_role_grant", False),
    }
    if role_store.get("_block_vendor_role_grant"):
        raise AppError(
            code="vendor_role_grant_failed",
            message="forced role grant failure",
            http_status=500,
        )

    kyc["status"] = "approved"
    kyc["reviewed_by"] = actor_id
    kyc["reviewed_at"] = "2026-01-01T00:00:00Z"
    kyc["decision_reason"] = notes
    if notes is not None:
        kyc["reviewer_notes"] = notes
    vendor["status"] = "active"
    vendor["kyc_tier"] = tier
    role_outcome = _upsert_vendor_role(role_store, owner)

    after = {
        "vendor": {
            "id": vendor["id"],
            "status": "active",
            "kyc_tier": tier,
        },
        "kyc_record": {
            "id": kyc["id"],
            "status": "approved",
            "tier": kyc["tier"],
            "reviewed_by": actor_id,
            "reviewed_at": kyc["reviewed_at"],
            "decision_reason": notes,
            "lifecycle_reason": kyc.get("lifecycle_reason"),
        },
        "vendor_role": {
            "user_id": owner,
            "role": "vendor",
            "outcome": role_outcome,
            "vendor_id": vendor["id"],
        },
    }
    audit_rows.append(
        {
            "actor": actor_id,
            "action": "kyc.approve",
            "entity_type": "kyc_record",
            "entity_id": kyc_id,
            "before": {"vendor": before_vendor, "kyc_record": before_kyc},
            "after": after,
        }
    )
    return after
