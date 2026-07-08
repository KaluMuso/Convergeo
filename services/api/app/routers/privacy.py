from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.supabase import get_user_client
from app.deps import SupabaseServiceClient, get_supabase_client
from app.errors import AppError
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from supabase import Client, create_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["privacy"])

PRIVATE_EXPORT_BUCKET = "private-artifacts"
EXPORT_PATH_PREFIX = "data-exports"
SIGNED_URL_TTL_SECONDS = 900
DELETE_CONFIRMATION_PHRASE = "DELETE MY ACCOUNT"
ANONYMOUS_DISPLAY_NAME = "Deleted User"

EXPORT_BUNDLE_KEYS = (
    "profile",
    "addresses",
    "checkout_groups",
    "orders",
    "order_items",
    "reviews",
    "disputes",
    "returns",
    "payments",
    "invoices",
    "flags",
)

PII_SNAPSHOT_KEYS = frozenset(
    {
        "name",
        "display_name",
        "full_name",
        "phone",
        "email",
        "address",
        "landmark",
        "delivery_address",
        "customer_name",
        "customer_phone",
        "recipient_name",
        "recipient_phone",
    }
)


class ExportResponse(BaseModel):
    export_id: str
    download_url: str
    expires_in_seconds: int


class DeleteAccountRequest(BaseModel):
    confirmation_phrase: str = Field(min_length=1)
    otp: str = Field(min_length=6, max_length=6)

    @field_validator("otp")
    @classmethod
    def validate_otp_digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("otp must contain digits only")
        return value


class DeleteAccountResponse(BaseModel):
    status: str
    user_id: str


def _normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        return digits
    if digits.startswith("260"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+260{digits[1:]}"
    return f"+{digits}"


def _table_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _maybe_single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    return None


def _redact_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[redacted]"
                if isinstance(key, str) and key.lower() in PII_SNAPSHOT_KEYS
                else _redact_json_value(nested)
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    return value


def assemble_export_bundle(user_client: Client, user_id: str) -> dict[str, Any]:
    profile_response = (
        user_client.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
    )
    profile = _maybe_single_row(profile_response)

    addresses = _table_rows(
        user_client.table("addresses").select("*").eq("user_id", user_id).execute()
    )
    checkout_groups = _table_rows(
        user_client.table("checkout_groups").select("*").eq("customer_id", user_id).execute()
    )
    orders = _table_rows(
        user_client.table("orders").select("*").eq("customer_id", user_id).execute()
    )
    order_ids = [row["id"] for row in orders if isinstance(row.get("id"), str)]

    order_items: list[dict[str, Any]] = []
    if order_ids:
        order_items = _table_rows(
            user_client.table("order_items").select("*").in_("order_id", order_ids).execute()
        )

    order_item_ids = [row["id"] for row in order_items if isinstance(row.get("id"), str)]

    reviews: list[dict[str, Any]] = []
    returns_rows: list[dict[str, Any]] = []
    if order_item_ids:
        reviews = _table_rows(
            user_client.table("reviews").select("*").in_("order_item_id", order_item_ids).execute()
        )
        returns_rows = _table_rows(
            user_client.table("returns").select("*").in_("order_item_id", order_item_ids).execute()
        )

    disputes: list[dict[str, Any]] = []
    if order_ids:
        disputes = _table_rows(
            user_client.table("disputes")
            .select("*")
            .in_("order_id", order_ids)
            .eq("opener_user_id", user_id)
            .execute()
        )

    checkout_group_ids = [row["id"] for row in checkout_groups if isinstance(row.get("id"), str)]
    payments: list[dict[str, Any]] = []
    if checkout_group_ids:
        payments = _table_rows(
            user_client.table("payments")
            .select("*")
            .in_("checkout_group_id", checkout_group_ids)
            .execute()
        )

    invoices: list[dict[str, Any]] = []
    if order_ids:
        invoices = _table_rows(
            user_client.table("invoices").select("*").in_("order_id", order_ids).execute()
        )

    flags = _table_rows(
        user_client.table("flags").select("*").eq("reporter_user_id", user_id).execute()
    )

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "user_id": user_id,
        "profile": profile,
        "addresses": addresses,
        "checkout_groups": checkout_groups,
        "orders": orders,
        "order_items": order_items,
        "reviews": reviews,
        "disputes": disputes,
        "returns": returns_rows,
        "payments": payments,
        "invoices": invoices,
        "flags": flags,
    }


def upload_export_bundle(
    service: SupabaseServiceClient,
    *,
    user_id: str,
    bundle: dict[str, Any],
) -> tuple[str, str]:
    export_id = str(uuid.uuid4())
    storage_path = f"{EXPORT_PATH_PREFIX}/{user_id}/{export_id}.json"
    payload = json.dumps(bundle, separators=(",", ":"), default=str).encode("utf-8")

    storage = service.client.storage.from_(PRIVATE_EXPORT_BUCKET)
    upload_response = storage.upload(
        storage_path,
        payload,
        {"content-type": "application/json", "upsert": "false"},
    )
    upload_error = getattr(upload_response, "error", None)
    if upload_error:
        raise AppError(
            code="export_upload_failed",
            message="Failed to store export bundle",
            http_status=500,
            details={"reason": str(upload_error)},
        )

    signed_response = storage.create_signed_url(storage_path, SIGNED_URL_TTL_SECONDS)
    signed_data = getattr(signed_response, "data", None) or signed_response
    if isinstance(signed_data, dict):
        download_url = signed_data.get("signedURL") or signed_data.get("signedUrl")
    else:
        download_url = None

    if not isinstance(download_url, str) or not download_url:
        raise AppError(
            code="export_sign_failed",
            message="Failed to sign export download URL",
            http_status=500,
        )

    return export_id, download_url


def verify_reauth_otp(*, phone: str | None, otp: str, settings: Settings) -> None:
    if not phone:
        raise AppError(
            code="reauth_required",
            message="Account deletion requires a verified phone number",
            http_status=403,
        )

    normalized_phone = _normalize_phone(phone)
    auth_client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = auth_client.auth.verify_otp(
            {"phone": normalized_phone, "token": otp, "type": "sms"},
        )
    except Exception as exc:
        raise AppError(
            code="reauth_failed",
            message="OTP verification failed",
            http_status=403,
            details={"reason": exc.__class__.__name__},
        ) from exc

    if getattr(response, "session", None) is None and getattr(response, "user", None) is None:
        raise AppError(
            code="reauth_failed",
            message="Invalid or expired OTP",
            http_status=403,
        )


def anonymize_and_delete_account(
    service: SupabaseServiceClient,
    *,
    user_id: str,
) -> None:
    db = service.client
    now_iso = datetime.now(UTC).isoformat()

    profile_response = (
        db.table("profiles")
        .select("id, deleted_at")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    profile = _maybe_single_row(profile_response)
    if profile and profile.get("deleted_at"):
        logger.info("Account deletion idempotent no-op", extra={"user_id": user_id})
        return

    orders = _table_rows(
        db.table("orders").select("id, address_id").eq("customer_id", user_id).execute()
    )
    order_ids = [row["id"] for row in orders if isinstance(row.get("id"), str)]
    order_item_ids: list[str] = []
    if order_ids:
        order_items = _table_rows(
            db.table("order_items").select("id").in_("order_id", order_ids).execute()
        )
        order_item_ids = [row["id"] for row in order_items if isinstance(row.get("id"), str)]

    db.table("addresses").delete().eq("user_id", user_id).execute()

    db.table("profiles").update(
        {
            "display_name": ANONYMOUS_DISPLAY_NAME,
            "phone": None,
            "notif_prefs": {},
            "deleted_at": now_iso,
        }
    ).eq("id", user_id).execute()

    if order_ids:
        db.table("orders").update(
            {
                "delivery_zone": None,
                "address_id": None,
            }
        ).in_("id", order_ids).execute()

    if order_item_ids:
        db.table("reviews").update(
            {
                "body": None,
                "photos": [],
            }
        ).in_("order_item_id", order_item_ids).execute()

        db.table("returns").update({"evidence_paths": []}).in_(
            "order_item_id", order_item_ids
        ).execute()

    if order_ids:
        db.table("disputes").update({"evidence_paths": []}).in_("order_id", order_ids).execute()

        invoices = _table_rows(
            db.table("invoices").select("id, snapshot").in_("order_id", order_ids).execute()
        )
        for invoice in invoices:
            invoice_id = invoice.get("id")
            if not isinstance(invoice_id, str):
                continue
            snapshot = invoice.get("snapshot")
            redacted_snapshot = _redact_json_value(snapshot if isinstance(snapshot, dict) else {})
            db.table("invoices").update({"snapshot": redacted_snapshot}).eq(
                "id", invoice_id
            ).execute()

        checkout_group_ids = _table_rows(
            db.table("checkout_groups").select("id").eq("customer_id", user_id).execute()
        )
        checkout_ids = [row["id"] for row in checkout_group_ids if isinstance(row.get("id"), str)]
        if checkout_ids:
            payments = _table_rows(
                db.table("payments")
                .select("id, raw")
                .in_("checkout_group_id", checkout_ids)
                .execute()
            )
            for payment in payments:
                payment_id = payment.get("id")
                if not isinstance(payment_id, str):
                    continue
                raw = payment.get("raw")
                redacted_raw = _redact_json_value(raw if isinstance(raw, dict) else {})
                db.table("payments").update({"raw": redacted_raw}).eq("id", payment_id).execute()

    try:
        db.auth.admin.delete_user(user_id)
    except Exception:
        db.auth.admin.update_user_by_id(
            user_id,
            {
                "phone": "",
                "email": "",
                "ban_duration": "876000h",
                "user_metadata": {"deleted": True, "deleted_at": now_iso},
            },
        )


@router.post("/export", response_model=ExportResponse)
async def export_account_data(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> ExportResponse:
    user_client = get_user_client(current_user.token, settings)
    bundle = assemble_export_bundle(user_client, current_user.id)

    missing = [key for key in EXPORT_BUNDLE_KEYS if key not in bundle]
    if missing:
        raise AppError(
            code="export_incomplete",
            message="Export bundle is missing required sections",
            http_status=500,
            details={"missing": missing},
        )

    export_id, download_url = upload_export_bundle(service, user_id=current_user.id, bundle=bundle)
    return ExportResponse(
        export_id=export_id,
        download_url=download_url,
        expires_in_seconds=SIGNED_URL_TTL_SECONDS,
    )


@router.post("/delete", response_model=DeleteAccountResponse)
async def delete_account(
    body: DeleteAccountRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> DeleteAccountResponse:
    if body.confirmation_phrase.strip() != DELETE_CONFIRMATION_PHRASE:
        raise AppError(
            code="confirmation_required",
            message="Confirmation phrase does not match",
            http_status=403,
        )

    profile_response = (
        service.client.table("profiles")
        .select("phone, deleted_at")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    profile = _maybe_single_row(profile_response)
    phone = profile.get("phone") if isinstance(profile, dict) else None
    if not isinstance(phone, str):
        phone = None

    verify_reauth_otp(phone=phone, otp=body.otp, settings=settings)
    anonymize_and_delete_account(service, user_id=current_user.id)

    return DeleteAccountResponse(status="deleted", user_id=current_user.id)
