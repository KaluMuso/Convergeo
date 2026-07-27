"""M18-P05 — vendor review of a WhatsApp intake draft, and the listing handoff.

This is the human gate in the D35 lane. Everything upstream of it (webhook →
media quarantine → rules-first extraction) produces a **proposal**; nothing
becomes a listing until the vendor opens this surface, sees exactly what was
extracted and **where each value came from**, corrects what is wrong, and
explicitly submits.

Boundaries this router keeps:

* **Ownership, always.** Every path loads the caller's own vendor row and
  matches it against the session's ``vendor_id``. A session belonging to another
  vendor is a 403 — including through a valid deep link, because the link is not
  the authorisation (see ``services/intake/deeplink.py``).
* **Never active-by-default.** Submission goes through
  ``vendor_listings.create_listing_for_vendor`` with ``publish=False``, so the
  listing lands in ``draft``. Activation is M18-P06's audited admin action.
* **KYC caps apply.** An intake-born listing counts against the same tier quota
  as one typed into the vendor app; the cap is enforced *before* the listing is
  created, not after.
* **Idempotent submission.** A session that already produced a listing returns
  that same listing rather than creating a second one.
* **Still inbound-only.** Nothing here sends a WhatsApp message. Follow-up
  questions are read from ``pending_requests`` and rendered by the vendor app.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_listings import create_listing_for_vendor
from app.schemas.base import StrictModel
from app.services.intake import deeplink, handoff, state_machine
from app.services.intake.schemas import Condition, PricingMode, StockMode
from app.services.kyc.caps import enforce_listing_cap, load_vendor_cap_limits_by_id
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(prefix="/vendor/intake", tags=["vendor-intake"])

DRAFT_TABLE: Final = "intake_draft_fields"
PROVENANCE_TABLE: Final = "intake_field_provenance"
MEDIA_TABLE: Final = "intake_media"
SESSIONS_TABLE: Final = "intake_sessions"

# Statuses a vendor may still act on. Terminal sessions are readable but frozen.
EDITABLE_STATUSES: Final[frozenset[str]] = frozenset(
    {state_machine.COLLECTING, state_machine.NEEDS_DETAILS, state_machine.READY_FOR_VENDOR_REVIEW}
)

MEDIA_URL_TTL_SECONDS: Final = 10 * 60
MAX_TITLE_LEN: Final = 200
MAX_DESCRIPTION_LEN: Final = 4_000


# --- Schemas ----------------------------------------------------------------
class IntakeSessionSummary(StrictModel):
    id: str
    status: str
    title: str | None
    price_ngwee: int | None
    pending_request_count: int
    listing_id: str | None
    last_activity_at: str | None


class FieldProvenanceOut(StrictModel):
    field_name: str
    source: str
    confidence: float | None
    model_ref: str | None


class IntakeMediaOut(StrictModel):
    id: str
    mime_type: str
    width_px: int | None
    height_px: int | None
    signed_url: str | None
    ttl_seconds: int


class PendingRequestOut(StrictModel):
    key: str
    field_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class IntakeDraftOut(StrictModel):
    title: str | None
    category_id: str | None
    price_ngwee: int | None
    pricing_mode: str | None
    quantity: int | None
    stock_mode: str | None
    sale_unit: str | None
    condition: str | None
    description: str | None


class IntakeSessionDetail(StrictModel):
    id: str
    status: str
    draft: IntakeDraftOut
    provenance: list[FieldProvenanceOut]
    media: list[IntakeMediaOut]
    pending_requests: list[PendingRequestOut]
    missing_fields: list[str]
    submittable: bool
    listing_id: str | None


class DraftPatchRequest(StrictModel):
    """Vendor corrections. Every supplied field flips provenance to vendor_typed."""

    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    category_id: str | None = None
    price_ngwee: int | None = Field(default=None, ge=0)
    pricing_mode: PricingMode | None = None
    quantity: int | None = Field(default=None, ge=0)
    stock_mode: StockMode | None = None
    sale_unit: str | None = Field(default=None, max_length=40)
    condition: Condition | None = None
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LEN)


class DeepLinkResponse(StrictModel):
    token: str
    session_id: str
    expires_at: str
    ttl_seconds: int


class RedeemLinkRequest(StrictModel):
    token: str = Field(min_length=1, max_length=512)


class SubmitResponse(StrictModel):
    session_id: str
    listing_id: str
    listing_status: str
    session_status: str
    already_submitted: bool


# --- Helpers ----------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _load_vendor(service_client: ServiceRoleClient, owner_user_id: str) -> dict[str, Any]:
    rows = _rows(
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    if not rows:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return rows[0]


def _load_owned_session(
    service_client: ServiceRoleClient, *, session_id: str, vendor_id: str
) -> dict[str, Any]:
    """Load a session, refusing anything the caller does not own.

    Ownership failure is a 403 with the same shape as a missing session so a
    vendor cannot enumerate another vendor's session ids by response code.
    """
    rows = _rows(
        service_client.client.table(SESSIONS_TABLE)
        .select("*")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not rows or str(rows[0].get("vendor_id")) != vendor_id:
        raise AppError(
            code="forbidden",
            message="Intake session is not accessible",
            http_status=403,
            details={"message_key": "vendor.intake.errors.notYours"},
        )
    return rows[0]


def _load_draft(service_client: ServiceRoleClient, session_id: str) -> dict[str, Any]:
    rows = _rows(
        service_client.client.table(DRAFT_TABLE)
        .select("*")
        .eq("session_id", session_id)
        .maybe_single()
        .execute()
    )
    return rows[0] if rows else {}


def _sign_media(service_client: ServiceRoleClient, session_id: str) -> list[IntakeMediaOut]:
    """Short-lived signed URLs for the private quarantine bucket (M13-P02 shape).

    A storage outage degrades to ``signed_url=None`` rather than failing the
    whole review page: the vendor can still correct text fields.
    """
    rows = _rows(
        service_client.client.table(MEDIA_TABLE)
        .select("id, storage_path, mime_type, width_px, height_px")
        .eq("session_id", session_id)
        .execute()
    )
    storage = getattr(service_client.client, "storage", None)
    bucket = storage.from_("vendor-intake-media") if storage is not None else None

    out: list[IntakeMediaOut] = []
    for row in rows:
        signed: str | None = None
        if bucket is not None:
            try:
                result = bucket.create_signed_url(
                    str(row["storage_path"]), MEDIA_URL_TTL_SECONDS
                )
                if isinstance(result, dict):
                    raw = (
                        result.get("signedURL")
                        or result.get("signedUrl")
                        or result.get("signed_url")
                    )
                    signed = str(raw) if raw else None
            except Exception:
                signed = None
        out.append(
            IntakeMediaOut(
                id=str(row["id"]),
                mime_type=str(row.get("mime_type") or ""),
                width_px=row.get("width_px"),
                height_px=row.get("height_px"),
                signed_url=signed,
                ttl_seconds=MEDIA_URL_TTL_SECONDS,
            )
        )
    return out


def _pending_requests(session: dict[str, Any]) -> list[PendingRequestOut]:
    raw = session.get("pending_requests")
    if not isinstance(raw, list):
        return []
    out: list[PendingRequestOut] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not isinstance(key, str):
            continue
        params = item.get("params")
        field_name = item.get("field_name")
        out.append(
            PendingRequestOut(
                key=key,
                field_name=field_name if isinstance(field_name, str) else None,
                params=(
                    {str(k): str(v) for k, v in params.items()}
                    if isinstance(params, dict)
                    else {}
                ),
            )
        )
    return out


def _draft_out(draft: dict[str, Any]) -> IntakeDraftOut:
    return IntakeDraftOut(
        title=draft.get("title"),
        category_id=str(draft["category_id"]) if draft.get("category_id") else None,
        price_ngwee=draft.get("price_ngwee"),
        pricing_mode=draft.get("pricing_mode"),
        quantity=draft.get("quantity"),
        stock_mode=draft.get("stock_mode"),
        sale_unit=draft.get("sale_unit"),
        condition=draft.get("condition"),
        description=draft.get("description"),
    )


def _detail(
    service_client: ServiceRoleClient, *, session: dict[str, Any]
) -> IntakeSessionDetail:
    session_id = str(session["id"])
    draft = _load_draft(service_client, session_id)
    provenance = _rows(
        service_client.client.table(PROVENANCE_TABLE)
        .select("field_name, source, confidence, model_ref")
        .eq("session_id", session_id)
        .execute()
    )
    missing = handoff.missing_fields(draft)
    return IntakeSessionDetail(
        id=session_id,
        status=str(session.get("status") or ""),
        draft=_draft_out(draft),
        provenance=[
            FieldProvenanceOut(
                field_name=str(row["field_name"]),
                source=str(row["source"]),
                confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
                model_ref=row.get("model_ref"),
            )
            for row in provenance
        ],
        media=_sign_media(service_client, session_id),
        pending_requests=_pending_requests(session),
        missing_fields=missing,
        submittable=not missing and str(session.get("status")) in EDITABLE_STATUSES,
        listing_id=str(session["listing_id"]) if session.get("listing_id") else None,
    )


def _rate_limit(
    service_client: ServiceRoleClient, *, scope: str, key: str, limit: int
) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=scope,
        key=key,
        window=timedelta(minutes=1),
        limit=limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="vendor.intake.errors.rateLimited",
            message="Too many intake requests",
        )


# --- Routes -----------------------------------------------------------------
@router.get("/sessions", response_model=list[IntakeSessionSummary])
async def list_intake_sessions(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[IntakeSessionSummary]:
    vendor = _load_vendor(service_client, current_user.id)
    sessions = _rows(
        service_client.client.table(SESSIONS_TABLE)
        .select("id, status, pending_requests, listing_id, last_activity_at")
        .eq("vendor_id", str(vendor["id"]))
        .order("last_activity_at", desc=True)
        .execute()
    )

    summaries: list[IntakeSessionSummary] = []
    for session in sessions:
        draft = _load_draft(service_client, str(session["id"]))
        pending = session.get("pending_requests")
        summaries.append(
            IntakeSessionSummary(
                id=str(session["id"]),
                status=str(session.get("status") or ""),
                title=draft.get("title"),
                price_ngwee=draft.get("price_ngwee"),
                pending_request_count=len(pending) if isinstance(pending, list) else 0,
                listing_id=str(session["listing_id"]) if session.get("listing_id") else None,
                last_activity_at=(
                    str(session["last_activity_at"]) if session.get("last_activity_at") else None
                ),
            )
        )
    return summaries


@router.get("/sessions/{session_id}", response_model=IntakeSessionDetail)
async def get_intake_session(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> IntakeSessionDetail:
    vendor = _load_vendor(service_client, current_user.id)
    session = _load_owned_session(
        service_client, session_id=session_id, vendor_id=str(vendor["id"])
    )
    return _detail(service_client, session=session)


@router.post("/sessions/{session_id}/link", response_model=DeepLinkResponse)
async def mint_review_link(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> DeepLinkResponse:
    """Mint a single-use, short-TTL link to one session.

    Delivery is Lane 1 / in-app only. This never reaches the WAHA lane, which is
    strictly inbound-only.
    """
    vendor = _load_vendor(service_client, current_user.id)
    _rate_limit(
        service_client, scope="intake_link_mint", key=str(vendor["id"]), limit=10
    )
    _load_owned_session(service_client, session_id=session_id, vendor_id=str(vendor["id"]))
    token, expires_at = deeplink.mint(service_client, session_id=session_id)
    return DeepLinkResponse(
        token=token,
        session_id=session_id,
        expires_at=expires_at.isoformat(),
        ttl_seconds=deeplink.DEFAULT_TTL_SECONDS,
    )


@router.post("/links/redeem", response_model=IntakeSessionDetail)
async def redeem_review_link(
    body: RedeemLinkRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> IntakeSessionDetail:
    """Consume a link and open its session.

    The authenticated vendor must own the session. Redemption alone grants
    nothing — a link forwarded to another vendor still 403s.
    """
    vendor = _load_vendor(service_client, current_user.id)
    _rate_limit(
        service_client, scope="intake_link_redeem", key=str(vendor["id"]), limit=20
    )
    session_id = deeplink.redeem(service_client, token=body.token)
    session = _load_owned_session(
        service_client, session_id=session_id, vendor_id=str(vendor["id"])
    )
    return _detail(service_client, session=session)


@router.patch("/sessions/{session_id}/draft", response_model=IntakeSessionDetail)
async def patch_intake_draft(
    session_id: str,
    body: DraftPatchRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> IntakeSessionDetail:
    """Apply vendor corrections and mark every touched field ``vendor_typed``."""
    vendor = _load_vendor(service_client, current_user.id)
    session = _load_owned_session(
        service_client, session_id=session_id, vendor_id=str(vendor["id"])
    )
    status = str(session.get("status") or "")
    if status not in EDITABLE_STATUSES:
        raise AppError(
            code="intake_session_not_editable",
            message="Intake session can no longer be edited",
            http_status=409,
            details={"message_key": "vendor.intake.errors.notEditable", "status": status},
        )

    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return _detail(service_client, session=session)

    payload: dict[str, Any] = {}
    for name, value in patch.items():
        payload[name] = value.value if hasattr(value, "value") else value

    existing = _rows(
        service_client.client.table(DRAFT_TABLE)
        .select("session_id")
        .eq("session_id", session_id)
        .maybe_single()
        .execute()
    )
    if existing:
        service_client.client.table(DRAFT_TABLE).update(payload).eq(
            "session_id", session_id
        ).execute()
    else:
        service_client.client.table(DRAFT_TABLE).insert(
            {"session_id": session_id, **payload}
        ).execute()

    # A human typed it. This is the highest provenance rank and M18-P04's
    # persistence refuses to downgrade it on a later inbound message.
    for name in payload:
        row = {
            "session_id": session_id,
            "field_name": name,
            "source": "vendor_typed",
            "confidence": None,
            "model_ref": None,
        }
        prior = _rows(
            service_client.client.table(PROVENANCE_TABLE)
            .select("session_id")
            .eq("session_id", session_id)
            .eq("field_name", name)
            .maybe_single()
            .execute()
        )
        if prior:
            service_client.client.table(PROVENANCE_TABLE).update(row).eq(
                "session_id", session_id
            ).eq("field_name", name).execute()
        else:
            service_client.client.table(PROVENANCE_TABLE).insert(row).execute()

    refreshed = _load_owned_session(
        service_client, session_id=session_id, vendor_id=str(vendor["id"])
    )
    return _detail(service_client, session=refreshed)


@router.post("/sessions/{session_id}/submit", response_model=SubmitResponse)
async def submit_intake_session(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> SubmitResponse:
    """The vendor's explicit act: turn a reviewed draft into a draft listing.

    Order matters. Ownership, then idempotency, then the KYC cap, then the
    listing (through the normal seam), then the guarded transitions. The listing
    id is written back to the session *before* the transitions so an interrupted
    request can never leave an orphaned listing the session does not know about.
    """
    vendor = _load_vendor(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    session = _load_owned_session(
        service_client, session_id=session_id, vendor_id=vendor_id
    )

    # Idempotent: a repeated submit returns the listing the first one produced.
    if session.get("listing_id"):
        listing_id = str(session["listing_id"])
        listing = _rows(
            service_client.client.table("vendor_listings")
            .select("id, status")
            .eq("id", listing_id)
            .maybe_single()
            .execute()
        )
        return SubmitResponse(
            session_id=session_id,
            listing_id=listing_id,
            listing_status=str(listing[0]["status"]) if listing else "draft",
            session_status=str(session.get("status") or ""),
            already_submitted=True,
        )

    status = str(session.get("status") or "")
    if status != state_machine.READY_FOR_VENDOR_REVIEW:
        raise AppError(
            code="intake_session_not_submittable",
            message="Intake session is not ready for submission",
            http_status=409,
            details={"message_key": "vendor.intake.errors.notReady", "status": status},
        )

    draft = _load_draft(service_client, session_id)
    listing_request = handoff.build_listing_request(draft)

    # Same tier quota as a hand-typed listing. Checked before anything is written.
    enforce_listing_cap(
        load_vendor_cap_limits_by_id(service_client, vendor_id, vendor_row=vendor)
    )

    created = create_listing_for_vendor(
        service_client, vendor=vendor, body=listing_request
    )
    if created.status != "draft":
        # Defensive: the intake path must never mint an active listing. If the
        # shared seam ever changed, fail loudly rather than publish silently.
        raise AppError(
            code="internal_error",
            message="Intake handoff produced a non-draft listing",
            http_status=500,
            details={"listing_status": created.status},
        )

    service_client.client.table(SESSIONS_TABLE).update(
        {
            "listing_id": created.listing_id,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", session_id).execute()

    state_machine.transition(
        service_client, session_id=session_id, to_status=state_machine.SUBMITTED
    )
    final = state_machine.transition(
        service_client,
        session_id=session_id,
        to_status=state_machine.PENDING_ADMIN_REVIEW,
    )

    return SubmitResponse(
        session_id=session_id,
        listing_id=created.listing_id,
        listing_status=created.status,
        session_status=str(final.get("status") or state_machine.PENDING_ADMIN_REVIEW),
        already_submitted=False,
    )
