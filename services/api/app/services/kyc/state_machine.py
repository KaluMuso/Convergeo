from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, cast
from uuid import UUID

from app.deps import get_supabase_service_client  # type: ignore[attr-defined]
from app.errors import AppError

# Canonical DB statuses after migration 0056. Legacy `pending` is still accepted
# on read (mapped to submitted) for mixed-environment safety during rollout.
KYC_RECORD_STATUSES = frozenset(
    {
        "submitted",
        "under_review",
        "approved",
        "rejected",
        "suspended",
        "revoked",
        "pending",  # legacy synonym for submitted
    }
)
REVIEWABLE_STATUSES = frozenset({"submitted", "under_review", "pending"})
VENDOR_STATUSES = frozenset({"draft", "pending_kyc", "active", "suspended"})
VALID_TIERS = frozenset({1, 2, 3})


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class KycApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class KycTransitionError(AppError):
    def __init__(self, message: str, *, from_status: str, to_status: str) -> None:
        super().__init__(
            code="kyc_invalid_transition",
            message=message,
            http_status=409,
            details={"from_status": from_status, "to_status": to_status},
        )


@dataclass(frozen=True, slots=True)
class KycRecordSnapshot:
    id: str
    vendor_id: str
    tier: int
    status: str
    db_status: str
    doc_storage_paths: list[str]
    momo_name_match: dict[str, Any] | None
    reviewer_notes: str | None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    decision_reason: str | None = None
    lifecycle_reason: str | None = None


@dataclass(frozen=True, slots=True)
class VendorSnapshot:
    id: str
    owner_user_id: str
    status: str
    kyc_tier: int | None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def _normalize_entity_id(entity_id: str | UUID | None) -> str | None:
    if entity_id is None:
        return None
    if isinstance(entity_id, UUID):
        return str(entity_id)
    value = entity_id.strip()
    return value or None


def normalize_record_status(status: str) -> str:
    """Map legacy pending → submitted for application/capability logic."""
    if status == "pending":
        return "submitted"
    return status


def write_kyc_audit_log(
    service_client: ServiceRoleClient,
    *,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str | UUID | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    row = {
        "actor": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": _normalize_entity_id(entity_id),
        "before": before,
        "after": after,
    }
    response = service_client.client.table("audit_log").insert(row).execute()
    data = response.data
    if not isinstance(data, list) or not data:
        raise AppError(
            code="audit_write_failed",
            message="Failed to persist KYC audit_log row",
            http_status=500,
        )
    return cast(dict[str, Any], data[0])


def _load_vendor(service_client: ServiceRoleClient, vendor_id: str) -> VendorSnapshot:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    return VendorSnapshot(
        id=str(row["id"]),
        owner_user_id=str(row["owner_user_id"]),
        status=str(row["status"]),
        kyc_tier=row.get("kyc_tier"),
    )


def _snapshot_from_row(row: dict[str, Any]) -> KycRecordSnapshot:
    paths = row.get("doc_storage_paths")
    doc_paths = [str(path) for path in paths] if isinstance(paths, list) else []
    momo = row.get("momo_name_match")
    momo_match = cast(dict[str, Any], momo) if isinstance(momo, dict) else None
    reviewer_notes = row.get("reviewer_notes")
    reviewed_by = row.get("reviewed_by")
    reviewed_at = row.get("reviewed_at")
    decision_reason = row.get("decision_reason")
    lifecycle_reason = row.get("lifecycle_reason")
    return KycRecordSnapshot(
        id=str(row["id"]),
        vendor_id=str(row["vendor_id"]),
        tier=int(row["tier"]),
        status=normalize_record_status(str(row["status"])),
        db_status=str(row["status"]),
        doc_storage_paths=doc_paths,
        momo_name_match=momo_match,
        reviewer_notes=str(reviewer_notes) if isinstance(reviewer_notes, str) else None,
        reviewed_by=str(reviewed_by) if reviewed_by else None,
        reviewed_at=str(reviewed_at) if reviewed_at else None,
        decision_reason=str(decision_reason) if isinstance(decision_reason, str) else None,
        lifecycle_reason=str(lifecycle_reason) if isinstance(lifecycle_reason, str) else None,
    )


_KYC_SELECT = (
    "id, vendor_id, tier, status, doc_storage_paths, momo_name_match, "
    "reviewer_notes, reviewed_by, reviewed_at, decision_reason, lifecycle_reason"
)


def _load_latest_kyc_record(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> KycRecordSnapshot | None:
    response = (
        service_client.client.table("kyc_records")
        .select(_KYC_SELECT)
        .eq("vendor_id", vendor_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    return _snapshot_from_row(rows[0])


def _load_kyc_record_by_id(
    service_client: ServiceRoleClient,
    kyc_record_id: str,
) -> KycRecordSnapshot | None:
    response = (
        service_client.client.table("kyc_records")
        .select(_KYC_SELECT)
        .eq("id", kyc_record_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    return _snapshot_from_row(row)


def derive_application_status(
    vendor: VendorSnapshot,
    kyc_record: KycRecordSnapshot | None,
) -> KycApplicationStatus:
    _ = vendor
    if kyc_record is None:
        return KycApplicationStatus.DRAFT
    status = normalize_record_status(kyc_record.status)
    if status == "approved":
        return KycApplicationStatus.APPROVED
    if status == "rejected":
        return KycApplicationStatus.REJECTED
    if status == "under_review":
        return KycApplicationStatus.UNDER_REVIEW
    if status == "submitted":
        return KycApplicationStatus.SUBMITTED
    if status == "suspended":
        return KycApplicationStatus.SUSPENDED
    if status == "revoked":
        return KycApplicationStatus.REVOKED
    return KycApplicationStatus.DRAFT


def _guard_transition(
    current: KycApplicationStatus,
    allowed_from: frozenset[KycApplicationStatus],
    target: KycApplicationStatus,
) -> None:
    if current not in allowed_from:
        raise KycTransitionError(
            f"Cannot transition from {current.value} to {target.value}",
            from_status=current.value,
            to_status=target.value,
        )


def _update_vendor(
    service_client: ServiceRoleClient,
    vendor_id: str,
    *,
    expected_status: str,
    status: str | None = None,
    kyc_tier: int | None = None,
    clear_kyc_tier: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = status
    if clear_kyc_tier:
        payload["kyc_tier"] = None
    elif kyc_tier is not None:
        payload["kyc_tier"] = kyc_tier
    if not payload:
        raise ValueError("vendor update requires at least one field")

    response = (
        service_client.client.table("vendors")
        .update(payload)
        .eq("id", vendor_id)
        .eq("status", expected_status)
        .execute()
    )
    row = _single_row(response)
    if row is None:
        rows = _rows(response)
        if not rows:
            raise AppError(
                code="kyc_transition_conflict",
                message="Concurrent transition changed vendor state",
                http_status=409,
            )
        row = rows[0]
    return row


def _insert_kyc_record(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    tier: int,
    doc_storage_paths: list[str],
    momo_name_match: dict[str, Any] | None,
    status: str = "submitted",
) -> dict[str, Any]:
    if tier not in VALID_TIERS:
        raise AppError(
            code="validation_error",
            message="KYC tier must be 1, 2, or 3",
            http_status=422,
        )
    write_status = normalize_record_status(status)
    if write_status not in KYC_RECORD_STATUSES - {"pending"}:
        raise AppError(
            code="validation_error",
            message="Invalid KYC record status",
            http_status=422,
        )

    row: dict[str, Any] = {
        "vendor_id": vendor_id,
        "tier": tier,
        "doc_storage_paths": doc_storage_paths,
        "momo_name_match": momo_name_match,
        "status": write_status,
    }
    response = service_client.client.table("kyc_records").insert(row).execute()
    inserted = _single_row(response)
    if inserted is None:
        rows = _rows(response)
        if rows:
            inserted = rows[0]
    if inserted is None:
        raise AppError(
            code="kyc_write_failed",
            message="Failed to create KYC record",
            http_status=500,
        )
    return inserted


def _update_kyc_record(
    service_client: ServiceRoleClient,
    kyc_record_id: str,
    *,
    expected_status: str,
    status: str | None = None,
    momo_name_match: dict[str, Any] | None = None,
    reviewer_notes: str | None = None,
    reviewed_by: str | None = None,
    reviewed_at: str | None = None,
    decision_reason: str | None = None,
    lifecycle_reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = normalize_record_status(status)
    if momo_name_match is not None:
        payload["momo_name_match"] = momo_name_match
    if reviewer_notes is not None:
        payload["reviewer_notes"] = reviewer_notes
    if reviewed_by is not None:
        payload["reviewed_by"] = reviewed_by
    if reviewed_at is not None:
        payload["reviewed_at"] = reviewed_at
    if decision_reason is not None:
        payload["decision_reason"] = decision_reason
    if lifecycle_reason is not None:
        payload["lifecycle_reason"] = lifecycle_reason
    if not payload:
        raise ValueError("kyc record update requires at least one field")

    response = (
        service_client.client.table("kyc_records")
        .update(payload)
        .eq("id", kyc_record_id)
        .eq("status", expected_status)
        .execute()
    )
    row = _single_row(response)
    if row is None:
        rows = _rows(response)
        if not rows:
            raise AppError(
                code="kyc_transition_conflict",
                message="Concurrent transition changed KYC record state",
                http_status=409,
            )
        row = rows[0]
    return row


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _record_audit_slice(record: KycRecordSnapshot | dict[str, Any]) -> dict[str, Any]:
    if isinstance(record, KycRecordSnapshot):
        return {
            "id": record.id,
            "status": record.status,
            "tier": record.tier,
            "reviewed_by": record.reviewed_by,
            "reviewed_at": record.reviewed_at,
            "decision_reason": record.decision_reason,
            "lifecycle_reason": record.lifecycle_reason,
        }
    return {
        "id": record.get("id"),
        "status": normalize_record_status(str(record.get("status", ""))),
        "tier": record.get("tier"),
        "reviewed_by": record.get("reviewed_by"),
        "reviewed_at": record.get("reviewed_at"),
        "decision_reason": record.get("decision_reason"),
        "lifecycle_reason": record.get("lifecycle_reason"),
    }


@dataclass(slots=True)
class KycStateMachine:
    service_client: ServiceRoleClient

    @classmethod
    def default(cls) -> KycStateMachine:
        return cls(get_supabase_service_client())

    def get_status(self, vendor_id: str) -> tuple[KycApplicationStatus, KycRecordSnapshot | None]:
        vendor = _load_vendor(self.service_client, vendor_id)
        kyc_record = _load_latest_kyc_record(self.service_client, vendor_id)
        return derive_application_status(vendor, kyc_record), kyc_record


def transition_submit(
    *,
    actor_id: str,
    vendor_id: str,
    tier: int,
    doc_storage_paths: list[str],
    momo_name_match: dict[str, Any] | None,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    client = service_client or get_supabase_service_client()
    vendor = _load_vendor(client, vendor_id)
    kyc_record = _load_latest_kyc_record(client, vendor_id)
    current = derive_application_status(vendor, kyc_record)
    _guard_transition(
        current,
        frozenset(
            {
                KycApplicationStatus.DRAFT,
                KycApplicationStatus.REJECTED,
                KycApplicationStatus.REVOKED,
            }
        ),
        KycApplicationStatus.SUBMITTED,
    )

    before = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_record) if kyc_record else None,
    }

    vendor_after = _update_vendor(
        client, vendor_id, expected_status=vendor.status, status="pending_kyc"
    )
    created = _insert_kyc_record(
        client,
        vendor_id=vendor_id,
        tier=tier,
        doc_storage_paths=doc_storage_paths,
        momo_name_match=momo_name_match,
        status="submitted",
    )

    after = {
        "vendor": {
            "id": vendor_after["id"],
            "status": vendor_after["status"],
            "kyc_tier": vendor_after.get("kyc_tier"),
        },
        "kyc_record": _record_audit_slice(created),
    }
    write_kyc_audit_log(
        client,
        actor_id=actor_id,
        action="kyc.submit",
        entity_type="kyc_record",
        entity_id=str(created["id"]),
        before=before,
        after=after,
    )
    return after


def transition_resubmit(
    *,
    actor_id: str,
    vendor_id: str,
    tier: int,
    doc_storage_paths: list[str],
    momo_name_match: dict[str, Any] | None,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    return transition_submit(
        actor_id=actor_id,
        vendor_id=vendor_id,
        tier=tier,
        doc_storage_paths=doc_storage_paths,
        momo_name_match=momo_name_match,
        service_client=service_client,
    )


def transition_start_review(
    *,
    actor_id: str,
    vendor_id: str,
    kyc_record_id: str,
    lifecycle_reason: str | None = None,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    client = service_client or get_supabase_service_client()
    vendor = _load_vendor(client, vendor_id)
    kyc_record = _load_kyc_record_by_id(client, kyc_record_id)
    if kyc_record is None or kyc_record.vendor_id != vendor_id:
        raise AppError(code="not_found", message="KYC record not found", http_status=404)

    current = derive_application_status(vendor, kyc_record)
    _guard_transition(
        current,
        frozenset({KycApplicationStatus.SUBMITTED, KycApplicationStatus.UNDER_REVIEW}),
        KycApplicationStatus.UNDER_REVIEW,
    )

    before = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_record),
    }

    if current == KycApplicationStatus.UNDER_REVIEW:
        kyc_after = {
            "id": kyc_record.id,
            "status": kyc_record.status,
            "tier": kyc_record.tier,
            "reviewed_by": kyc_record.reviewed_by,
            "reviewed_at": kyc_record.reviewed_at,
            "decision_reason": kyc_record.decision_reason,
            "lifecycle_reason": kyc_record.lifecycle_reason,
        }
    else:
        kyc_after = _update_kyc_record(
            client,
            kyc_record_id,
            expected_status=kyc_record.db_status,
            status="under_review",
            lifecycle_reason=lifecycle_reason,
        )

    after = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_after),
    }
    write_kyc_audit_log(
        client,
        actor_id=actor_id,
        action="kyc.start_review",
        entity_type="kyc_record",
        entity_id=kyc_record_id,
        before=before,
        after=after,
    )
    return after


def transition_approve(
    *,
    actor_id: str,
    vendor_id: str,
    kyc_record_id: str,
    tier: int,
    reviewer_notes: str | None = None,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    client = service_client or get_supabase_service_client()
    vendor = _load_vendor(client, vendor_id)
    kyc_record = _load_kyc_record_by_id(client, kyc_record_id)
    if kyc_record is None or kyc_record.vendor_id != vendor_id:
        raise AppError(code="not_found", message="KYC record not found", http_status=404)

    current = derive_application_status(vendor, kyc_record)
    _guard_transition(
        current,
        frozenset({KycApplicationStatus.SUBMITTED, KycApplicationStatus.UNDER_REVIEW}),
        KycApplicationStatus.APPROVED,
    )

    momo = kyc_record.momo_name_match or {}
    if momo.get("matched") is False:
        raise AppError(
            code="kyc_name_match_required",
            message="KYC cannot be approved while MoMo name-match is flagged",
            http_status=409,
            details={"message_key": "vendor.kyc.name_match_mismatch"},
        )

    if tier != kyc_record.tier:
        raise AppError(
            code="validation_error",
            message="Approval tier must match the KYC record tier",
            http_status=422,
            details={"record_tier": kyc_record.tier, "requested_tier": tier},
        )

    before = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_record),
    }

    decision_reason = reviewer_notes
    reviewed_at = _utc_now_iso()
    kyc_after = _update_kyc_record(
        client,
        kyc_record_id,
        expected_status=kyc_record.db_status,
        status="approved",
        reviewer_notes=reviewer_notes,
        reviewed_by=actor_id,
        reviewed_at=reviewed_at,
        decision_reason=decision_reason,
    )
    vendor_after = _update_vendor(
        client,
        vendor_id,
        expected_status=vendor.status,
        status="active",
        kyc_tier=tier,
    )

    after = {
        "vendor": {
            "id": vendor_after["id"],
            "status": vendor_after["status"],
            "kyc_tier": vendor_after.get("kyc_tier"),
        },
        "kyc_record": _record_audit_slice(kyc_after),
    }
    write_kyc_audit_log(
        client,
        actor_id=actor_id,
        action="kyc.approve",
        entity_type="kyc_record",
        entity_id=kyc_record_id,
        before=before,
        after=after,
    )
    return after


def transition_reject(
    *,
    actor_id: str,
    vendor_id: str,
    kyc_record_id: str,
    reviewer_notes: str,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    client = service_client or get_supabase_service_client()
    vendor = _load_vendor(client, vendor_id)
    kyc_record = _load_kyc_record_by_id(client, kyc_record_id)
    if kyc_record is None or kyc_record.vendor_id != vendor_id:
        raise AppError(code="not_found", message="KYC record not found", http_status=404)

    current = derive_application_status(vendor, kyc_record)
    if current == KycApplicationStatus.REJECTED:
        raise AppError(
            code="kyc_transition_conflict",
            message="KYC record already rejected",
            http_status=409,
        )
    _guard_transition(
        current,
        frozenset({KycApplicationStatus.SUBMITTED, KycApplicationStatus.UNDER_REVIEW}),
        KycApplicationStatus.REJECTED,
    )

    before = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_record),
    }

    reviewed_at = _utc_now_iso()
    kyc_after = _update_kyc_record(
        client,
        kyc_record_id,
        expected_status=kyc_record.db_status,
        status="rejected",
        reviewer_notes=reviewer_notes,
        reviewed_by=actor_id,
        reviewed_at=reviewed_at,
        decision_reason=reviewer_notes,
    )

    after = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_after),
    }
    write_kyc_audit_log(
        client,
        actor_id=actor_id,
        action="kyc.reject",
        entity_type="kyc_record",
        entity_id=kyc_record_id,
        before=before,
        after=after,
    )
    return after


def transition_suspend(
    *,
    actor_id: str,
    vendor_id: str,
    kyc_record_id: str,
    reason: str,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    client = service_client or get_supabase_service_client()
    vendor = _load_vendor(client, vendor_id)
    kyc_record = _load_kyc_record_by_id(client, kyc_record_id)
    if kyc_record is None or kyc_record.vendor_id != vendor_id:
        raise AppError(code="not_found", message="KYC record not found", http_status=404)

    current = derive_application_status(vendor, kyc_record)
    _guard_transition(
        current,
        frozenset({KycApplicationStatus.APPROVED}),
        KycApplicationStatus.SUSPENDED,
    )

    before = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_record),
    }

    kyc_after = _update_kyc_record(
        client,
        kyc_record_id,
        expected_status=kyc_record.db_status,
        status="suspended",
        lifecycle_reason=reason,
        reviewer_notes=reason,
    )
    # Clear denormalized tier immediately — eligibility already ignores non-approved.
    vendor_after = _update_vendor(
        client,
        vendor_id,
        expected_status=vendor.status,
        status="suspended",
        clear_kyc_tier=True,
    )

    after = {
        "vendor": {
            "id": vendor_after["id"],
            "status": vendor_after["status"],
            "kyc_tier": vendor_after.get("kyc_tier"),
        },
        "kyc_record": _record_audit_slice(kyc_after),
    }
    write_kyc_audit_log(
        client,
        actor_id=actor_id,
        action="kyc.suspend",
        entity_type="kyc_record",
        entity_id=kyc_record_id,
        before=before,
        after=after,
    )
    return after


def transition_revoke(
    *,
    actor_id: str,
    vendor_id: str,
    kyc_record_id: str,
    reason: str,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    client = service_client or get_supabase_service_client()
    vendor = _load_vendor(client, vendor_id)
    kyc_record = _load_kyc_record_by_id(client, kyc_record_id)
    if kyc_record is None or kyc_record.vendor_id != vendor_id:
        raise AppError(code="not_found", message="KYC record not found", http_status=404)

    current = derive_application_status(vendor, kyc_record)
    _guard_transition(
        current,
        frozenset({KycApplicationStatus.APPROVED, KycApplicationStatus.SUSPENDED}),
        KycApplicationStatus.REVOKED,
    )

    before = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "kyc_record": _record_audit_slice(kyc_record),
    }

    kyc_after = _update_kyc_record(
        client,
        kyc_record_id,
        expected_status=kyc_record.db_status,
        status="revoked",
        lifecycle_reason=reason,
        reviewer_notes=reason,
    )
    vendor_after = _update_vendor(
        client,
        vendor_id,
        expected_status=vendor.status,
        status="draft",
        clear_kyc_tier=True,
    )

    after = {
        "vendor": {
            "id": vendor_after["id"],
            "status": vendor_after["status"],
            "kyc_tier": vendor_after.get("kyc_tier"),
        },
        "kyc_record": _record_audit_slice(kyc_after),
    }
    write_kyc_audit_log(
        client,
        actor_id=actor_id,
        action="kyc.revoke",
        entity_type="kyc_record",
        entity_id=kyc_record_id,
        before=before,
        after=after,
    )
    return after


def transition_upgrade_tier(
    *,
    actor_id: str,
    vendor_id: str,
    target_tier: int,
    doc_storage_paths: list[str],
    momo_name_match: dict[str, Any] | None,
    service_client: ServiceRoleClient | None = None,
) -> dict[str, Any]:
    client = service_client or get_supabase_service_client()
    vendor = _load_vendor(client, vendor_id)
    if vendor.status != "active":
        raise AppError(
            code="kyc_invalid_transition",
            message="Tier upgrade requires an active vendor",
            http_status=409,
        )
    # Upgrade eligibility must be backed by an approved record, not a bare tier.
    from app.services.kyc.eligibility import resolve_vendor_eligibility

    eligibility = resolve_vendor_eligibility(client, vendor_id)
    if not eligibility.is_auditable_approved or eligibility.effective_tier is None:
        raise AppError(
            code="kyc_required",
            message="Tier upgrade requires an auditable approved KYC record",
            http_status=403,
        )
    current_tier = eligibility.effective_tier
    if target_tier not in VALID_TIERS or target_tier <= current_tier:
        raise AppError(
            code="validation_error",
            message="Target tier must be higher than the current tier",
            http_status=422,
            details={"current_tier": current_tier, "target_tier": target_tier},
        )

    before = {
        "vendor": {"id": vendor.id, "status": vendor.status, "kyc_tier": vendor.kyc_tier},
        "eligibility": eligibility.to_public_dict(),
    }
    created = _insert_kyc_record(
        client,
        vendor_id=vendor_id,
        tier=target_tier,
        doc_storage_paths=doc_storage_paths,
        momo_name_match=momo_name_match,
        status="submitted",
    )
    vendor_after = _update_vendor(
        client, vendor_id, expected_status=vendor.status, status="pending_kyc"
    )

    after = {
        "vendor": {
            "id": vendor_after["id"],
            "status": vendor_after["status"],
            "kyc_tier": vendor_after.get("kyc_tier"),
        },
        "kyc_record": _record_audit_slice(created),
    }
    write_kyc_audit_log(
        client,
        actor_id=actor_id,
        action="kyc.upgrade_tier",
        entity_type="vendor",
        entity_id=vendor_id,
        before=before,
        after=after,
    )
    return after
