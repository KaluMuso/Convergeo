"""Vendor-to-organiser event collaboration (flag ``events_collaboration``, default OFF).

A vendor without organiser KYC proposes an event to a verified, opted-in
organiser. Statuses change only through ``public.event_collab_transition``
(guarded + audited); every handler authorises the caller as a PARTY of the
request (proposer or organiser) and answers 404 for anyone else so request ids
cannot be probed. Publishing creates the event under the ORGANISER's account;
the co-host and the integer-basis-point split are recorded for the ledger only
(payouts are OFF in the pilot).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final, Literal, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import POLICIES, RateLimitPolicy, route_id
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.collaboration import (
    EDITABLE_STATUSES,
    MAX_BPS,
    Checklist,
    EventDraft,
    assert_submittable,
    assert_transition_allowed,
    call_transition,
    readiness_pct,
)
from fastapi import APIRouter, Depends, Query
from pydantic import Field

router = APIRouter(prefix="/vendor/event-collaboration", tags=["event-collaboration"])

FLAG: Final = "events_collaboration"
REQUESTS: Final = "event_collab_requests"
_UUID_RE: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_REQUEST_COLUMNS: Final = (
    "id, proposer_vendor_id, organiser_vendor_id, status, event_draft, checklist, "
    "readiness_pct, revenue_share_bps, organiser_note, event_id, submitted_at, "
    "decided_at, published_at, created_at, updated_at"
)
PROPOSER_VENDOR_STATUSES: Final = frozenset({"active", "pending_kyc"})

WRITE_POLICY: Final = RateLimitPolicy(
    scope="event_collab_write", limit=30, window=timedelta(minutes=1)
)
READ_POLICY: Final = RateLimitPolicy(
    scope="event_collab_read", limit=120, window=timedelta(minutes=1)
)
for _method, _path in (
    ("PUT", "/vendor/event-collaboration/organiser-settings"),
    ("POST", "/vendor/event-collaboration/requests"),
    ("PATCH", "/vendor/event-collaboration/requests/{request_id}"),
    ("POST", "/vendor/event-collaboration/requests/{request_id}/submit"),
    ("POST", "/vendor/event-collaboration/requests/{request_id}/approve"),
    ("POST", "/vendor/event-collaboration/requests/{request_id}/decline"),
    ("POST", "/vendor/event-collaboration/requests/{request_id}/request-changes"),
    ("POST", "/vendor/event-collaboration/requests/{request_id}/publish"),
):
    POLICIES.setdefault(route_id(_method, _path), WRITE_POLICY)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ----------------------------------------------------------------------
class CollabStatus(StrictModel):
    enabled: bool
    can_organise: bool
    accepts_requests: bool


class OrganiserSettingsRequest(StrictModel):
    accepts_requests: bool
    blurb: str | None = Field(default=None, max_length=280)


class OrganiserOption(StrictModel):
    vendor_id: str
    slug: str
    display_name: str
    blurb: str | None = None


class OrganiserList(StrictModel):
    items: list[OrganiserOption]


class RequestCreate(StrictModel):
    organiser_vendor_id: str = Field(pattern=_UUID_RE.pattern)
    event_draft: EventDraft = Field(default_factory=EventDraft)
    checklist: Checklist = Field(default_factory=Checklist)
    revenue_share_bps: int | None = Field(default=None, ge=0, le=MAX_BPS)


class RequestPatch(StrictModel):
    event_draft: EventDraft | None = None
    checklist: Checklist | None = None
    revenue_share_bps: int | None = Field(default=None, ge=0, le=MAX_BPS)


class ReasonBody(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)


class PartyView(StrictModel):
    vendor_id: str
    display_name: str
    slug: str | None = None


class AuditView(StrictModel):
    action: str
    actor_role: str
    from_status: str | None
    to_status: str
    reason: str | None
    created_at: str


class RequestView(StrictModel):
    id: str
    status: str
    my_role: Literal["proposer", "organiser"]
    proposer: PartyView
    organiser: PartyView
    event_draft: dict[str, Any]
    checklist: dict[str, Any]
    readiness_pct: int
    revenue_share_bps: int | None
    organiser_note: str | None
    event_id: str | None
    submitted_at: str | None
    decided_at: str | None
    published_at: str | None
    created_at: str
    updated_at: str
    audit: list[AuditView] = Field(default_factory=list)


class RequestList(StrictModel):
    items: list[RequestView]


# --- Helpers ----------------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _first(response: Any) -> dict[str, Any] | None:
    rows = _rows(response)
    return rows[0] if rows else None


def _limit(service_client: ServiceRoleClient, user_id: str, policy: RateLimitPolicy) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=policy.scope,
        key=user_id,
        window=policy.window,
        limit=policy.limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="vendor.events.collab.errors.rateLimited",
            message="Too many collaboration requests",
        )


def _flag_enabled(service_client: ServiceRoleClient) -> bool:
    """Read ``feature_flags.events_collaboration`` fresh; fail closed."""
    try:
        row = _first(
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", FLAG)
            .maybe_single()
            .execute()
        )
    except Exception:
        return False
    return bool(row and row.get("enabled") is True)


def _require_flag(service_client: ServiceRoleClient) -> None:
    if not _flag_enabled(service_client):
        raise AppError(
            code="feature_disabled",
            message="Event collaboration is not available",
            http_status=404,
            details={"message_key": "vendor.events.collab.errors.disabled"},
        )


def _load_vendor(service_client: ServiceRoleClient, user_id: str) -> dict[str, Any]:
    row = _first(
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier, slug, display_name")
        .eq("owner_user_id", user_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _can_organise(service_client: ServiceRoleClient, vendor: dict[str, Any]) -> bool:
    from app.services.kyc.eligibility import resolve_vendor_eligibility

    eligibility = resolve_vendor_eligibility(service_client, str(vendor["id"]), vendor_row=vendor)
    return eligibility.can_organise_events


def _require_organiser_eligible(service_client: ServiceRoleClient, vendor: dict[str, Any]) -> None:
    from app.services.kyc.eligibility import require_events_eligible, resolve_vendor_eligibility

    require_events_eligible(
        resolve_vendor_eligibility(service_client, str(vendor["id"]), vendor_row=vendor)
    )


def _not_found() -> AppError:
    return AppError(
        code="not_found",
        message="Request not found",
        http_status=404,
        details={"message_key": "vendor.events.collab.errors.notFound"},
    )


def _load_request_for_party(
    service_client: ServiceRoleClient, request_id: str, vendor_id: str
) -> tuple[dict[str, Any], Literal["proposer", "organiser"]]:
    """Load a request the caller is a party to; anyone else gets 404."""
    if not _UUID_RE.match(request_id):
        raise _not_found()
    row = _first(
        service_client.client.table(REQUESTS)
        .select(_REQUEST_COLUMNS)
        .eq("id", request_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise _not_found()
    if str(row["organiser_vendor_id"]) == vendor_id:
        if row.get("status") == "draft":
            # Organisers never learn about a proposer's unsent drafts.
            raise _not_found()
        return row, "organiser"
    if str(row["proposer_vendor_id"]) == vendor_id:
        return row, "proposer"
    raise _not_found()


def _parties(
    service_client: ServiceRoleClient, rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    ids = sorted(
        {str(r["proposer_vendor_id"]) for r in rows} | {str(r["organiser_vendor_id"]) for r in rows}
    )
    if not ids:
        return {}
    vendors = _rows(
        service_client.client.table("vendors")
        .select("id, slug, display_name")
        .in_("id", ids)
        .execute()
    )
    return {str(v["id"]): v for v in vendors}


def _party(vendor_id: str, vendors: dict[str, dict[str, Any]]) -> PartyView:
    v = vendors.get(vendor_id, {})
    return PartyView(
        vendor_id=vendor_id,
        display_name=str(v.get("display_name") or ""),
        slug=str(v["slug"]) if v.get("slug") else None,
    )


def _iso(value: Any) -> str | None:
    return None if value is None else str(value)


def _view(
    row: dict[str, Any],
    role: Literal["proposer", "organiser"],
    vendors: dict[str, dict[str, Any]],
    audit: list[dict[str, Any]] | None = None,
) -> RequestView:
    share = row.get("revenue_share_bps")
    return RequestView(
        id=str(row["id"]),
        status=str(row["status"]),
        my_role=role,
        proposer=_party(str(row["proposer_vendor_id"]), vendors),
        organiser=_party(str(row["organiser_vendor_id"]), vendors),
        event_draft=dict(row.get("event_draft") or {}),
        checklist=dict(row.get("checklist") or {}),
        readiness_pct=int(row.get("readiness_pct") or 0),
        revenue_share_bps=int(share) if share is not None else None,
        organiser_note=row.get("organiser_note"),
        event_id=str(row["event_id"]) if row.get("event_id") else None,
        submitted_at=_iso(row.get("submitted_at")),
        decided_at=_iso(row.get("decided_at")),
        published_at=_iso(row.get("published_at")),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        audit=[
            AuditView(
                action=str(a["action"]),
                actor_role=str(a["actor_role"]),
                from_status=a.get("from_status"),
                to_status=str(a["to_status"]),
                reason=a.get("reason"),
                created_at=str(a.get("created_at") or ""),
            )
            for a in (audit or [])
        ],
    )


def _detail(
    service_client: ServiceRoleClient,
    row: dict[str, Any],
    role: Literal["proposer", "organiser"],
) -> RequestView:
    audit = _rows(
        service_client.client.table("event_collab_audit")
        .select("action, actor_role, from_status, to_status, reason, created_at")
        .eq("request_id", str(row["id"]))
        .order("id")
        .execute()
    )
    return _view(row, role, _parties(service_client, [row]), audit)


def _stored_pieces(row: dict[str, Any]) -> tuple[EventDraft, Checklist, int | None]:
    share = row.get("revenue_share_bps")
    return (
        EventDraft.model_validate(row.get("event_draft") or {}),
        Checklist.model_validate(row.get("checklist") or {}),
        int(share) if share is not None else None,
    )


# --- Status + organiser opt-in ------------------------------------------------------
@router.get("/status", response_model=CollabStatus)
async def collaboration_status(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CollabStatus:
    enabled = _flag_enabled(service_client)
    if not enabled:
        return CollabStatus(enabled=False, can_organise=False, accepts_requests=False)
    vendor = _load_vendor(service_client, current_user.id)
    pref = _first(
        service_client.client.table("event_collab_organiser_prefs")
        .select("accepts_requests")
        .eq("vendor_id", str(vendor["id"]))
        .maybe_single()
        .execute()
    )
    return CollabStatus(
        enabled=True,
        can_organise=_can_organise(service_client, vendor),
        accepts_requests=bool(pref and pref.get("accepts_requests")),
    )


@router.put("/organiser-settings", response_model=CollabStatus)
async def set_organiser_settings(
    body: OrganiserSettingsRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CollabStatus:
    _require_flag(service_client)
    _limit(service_client, current_user.id, WRITE_POLICY)
    vendor = _load_vendor(service_client, current_user.id)
    # Only verified organisers can opt in (also keeps non-organisers off the list).
    _require_organiser_eligible(service_client, vendor)
    service_client.client.table("event_collab_organiser_prefs").upsert(
        {
            "vendor_id": str(vendor["id"]),
            "accepts_requests": body.accepts_requests,
            "blurb": (body.blurb or "").strip() or None,
        },
        on_conflict="vendor_id",
    ).execute()
    return CollabStatus(enabled=True, can_organise=True, accepts_requests=body.accepts_requests)


@router.get("/organisers", response_model=OrganiserList)
async def list_organisers(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    q: Annotated[str | None, Query(max_length=80)] = None,
) -> OrganiserList:
    """Verified organisers who opted in; never includes the caller."""
    _require_flag(service_client)
    _limit(service_client, current_user.id, READ_POLICY)
    me = _load_vendor(service_client, current_user.id)
    prefs = _rows(
        service_client.client.table("event_collab_organiser_prefs")
        .select("vendor_id, blurb")
        .eq("accepts_requests", True)
        .limit(500)
        .execute()
    )
    blurbs = {
        str(p["vendor_id"]): p.get("blurb") for p in prefs if str(p["vendor_id"]) != str(me["id"])
    }
    if not blurbs:
        return OrganiserList(items=[])
    vendors = _rows(
        service_client.client.table("vendors")
        .select("id, slug, display_name, status, kyc_tier, preferred_badge")
        .in_("id", sorted(blurbs))
        .eq("status", "active")
        .execute()
    )
    from app.services.kyc.eligibility import load_approved_tiers_for_client

    tiers = load_approved_tiers_for_client(service_client.client, [str(v["id"]) for v in vendors])
    needle = (q or "").strip().casefold()
    items = [
        OrganiserOption(
            vendor_id=str(v["id"]),
            slug=str(v["slug"]),
            display_name=str(v["display_name"]),
            blurb=blurbs.get(str(v["id"])),
        )
        for v in sorted(vendors, key=lambda v: str(v["display_name"]).casefold())
        if tiers.get(str(v["id"]), 0) >= 1
        and (not needle or needle in str(v["display_name"]).casefold())
    ][:50]
    return OrganiserList(items=items)


# --- Requests ---------------------------------------------------------------------
@router.post("/requests", response_model=RequestView)
async def create_request(
    body: RequestCreate,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    _require_flag(service_client)
    _limit(service_client, current_user.id, WRITE_POLICY)
    me = _load_vendor(service_client, current_user.id)
    my_id = str(me["id"])
    if str(me.get("status")) not in PROPOSER_VENDOR_STATUSES:
        raise AppError(
            code="forbidden",
            message="Your shop cannot propose events right now",
            http_status=403,
            details={"message_key": "vendor.events.collab.errors.proposerNotActive"},
        )
    if body.organiser_vendor_id == my_id:
        raise AppError(
            code="validation_error",
            message="Choose a different organiser",
            http_status=422,
            details={"message_key": "vendor.events.collab.errors.selfOrganiser"},
        )
    organiser = _first(
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier, slug, display_name")
        .eq("id", body.organiser_vendor_id)
        .maybe_single()
        .execute()
    )
    pref = _first(
        service_client.client.table("event_collab_organiser_prefs")
        .select("accepts_requests")
        .eq("vendor_id", body.organiser_vendor_id)
        .maybe_single()
        .execute()
    )
    if (
        organiser is None
        or not (pref and pref.get("accepts_requests") is True)
        or not _can_organise(service_client, organiser)
    ):
        raise AppError(
            code="organiser_unavailable",
            message="That organiser is not accepting requests",
            http_status=422,
            details={"message_key": "vendor.events.collab.errors.organiserUnavailable"},
        )
    inserted = _first(
        service_client.client.table(REQUESTS)
        .insert(
            {
                "proposer_vendor_id": my_id,
                "organiser_vendor_id": body.organiser_vendor_id,
                "event_draft": body.event_draft.model_dump(mode="json", exclude_none=True),
                "checklist": body.checklist.model_dump(mode="json"),
                "readiness_pct": readiness_pct(body.checklist, body.revenue_share_bps),
                "revenue_share_bps": body.revenue_share_bps,
            }
        )
        .execute()
    )
    if inserted is None:
        raise AppError(code="internal_error", message="Could not create request", http_status=500)
    service_client.client.rpc(
        "event_collab_record_create",
        {"p_request_id": str(inserted["id"]), "p_actor_user_id": current_user.id},
    ).execute()
    return _detail(service_client, inserted, "proposer")


@router.get("/requests", response_model=RequestList)
async def list_requests(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    role: Annotated[Literal["proposer", "organiser"], Query()] = "proposer",
) -> RequestList:
    _require_flag(service_client)
    _limit(service_client, current_user.id, READ_POLICY)
    me = _load_vendor(service_client, current_user.id)
    column = "proposer_vendor_id" if role == "proposer" else "organiser_vendor_id"
    query = (
        service_client.client.table(REQUESTS)
        .select(_REQUEST_COLUMNS)
        .eq(column, str(me["id"]))
        .order("updated_at", desc=True)
        .limit(100)
    )
    rows = _rows(query.execute())
    if role == "organiser":
        # Organisers never see another vendor's unsent drafts.
        rows = [r for r in rows if r.get("status") != "draft"]
    vendors = _parties(service_client, rows)
    return RequestList(items=[_view(r, role, vendors) for r in rows])


@router.get("/requests/{request_id}", response_model=RequestView)
async def get_request(
    request_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    _require_flag(service_client)
    _limit(service_client, current_user.id, READ_POLICY)
    me = _load_vendor(service_client, current_user.id)
    row, role = _load_request_for_party(service_client, request_id, str(me["id"]))
    return _detail(service_client, row, role)


@router.patch("/requests/{request_id}", response_model=RequestView)
async def update_request(
    request_id: str,
    body: RequestPatch,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    _require_flag(service_client)
    _limit(service_client, current_user.id, WRITE_POLICY)
    me = _load_vendor(service_client, current_user.id)
    row, role = _load_request_for_party(service_client, request_id, str(me["id"]))
    if role != "proposer":
        raise AppError(
            code="forbidden",
            message="Only the proposing vendor can edit the request",
            http_status=403,
            details={"message_key": "vendor.events.collab.errors.forbidden"},
        )
    status = str(row["status"])
    if status not in EDITABLE_STATUSES:
        raise AppError(
            code="invalid_transition",
            message=f"A {status} request can no longer be edited",
            http_status=409,
            details={
                "message_key": "vendor.events.collab.errors.notEditable",
                "from_status": status,
            },
        )
    draft, checklist, share = _stored_pieces(row)
    if body.event_draft is not None:
        draft = body.event_draft
    if body.checklist is not None:
        checklist = body.checklist
    if body.revenue_share_bps is not None:
        share = body.revenue_share_bps
    updated = _first(
        service_client.client.table(REQUESTS)
        .update(
            {
                "event_draft": draft.model_dump(mode="json", exclude_none=True),
                "checklist": checklist.model_dump(mode="json"),
                "readiness_pct": readiness_pct(checklist, share),
                "revenue_share_bps": share,
            }
        )
        .eq("id", request_id)
        .eq("status", status)
        .execute()
    )
    if updated is None:
        raise AppError(
            code="invalid_transition",
            message="The request changed while you were editing",
            http_status=409,
            details={"message_key": "vendor.events.collab.errors.invalidTransition"},
        )
    return _detail(service_client, updated, "proposer")


def _act(
    request_id: str,
    action: str,
    current_user: CurrentUser,
    service_client: ServiceRoleClient,
    *,
    reason: str | None = None,
    event_slug: str | None = None,
    extra_check: Any = None,
) -> RequestView:
    _require_flag(service_client)
    _limit(service_client, current_user.id, WRITE_POLICY)
    me = _load_vendor(service_client, current_user.id)
    row, role = _load_request_for_party(service_client, request_id, str(me["id"]))
    assert_transition_allowed(action, role=role, status=str(row["status"]))
    if extra_check is not None:
        prepared = extra_check(row, me)
        if isinstance(prepared, str):
            event_slug = prepared
    updated = call_transition(
        service_client,
        request_id=request_id,
        actor_user_id=current_user.id,
        action=action,
        reason=reason,
        event_slug=event_slug,
    )
    merged = {**row, **updated}
    return _detail(service_client, merged, role)


@router.post("/requests/{request_id}/submit", response_model=RequestView)
async def submit_request(
    request_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    def check(row: dict[str, Any], _me: dict[str, Any]) -> None:
        draft, checklist, share = _stored_pieces(row)
        assert_submittable(draft, checklist, share)
        organiser = _first(
            service_client.client.table("vendors")
            .select("id, status, kyc_tier")
            .eq("id", str(row["organiser_vendor_id"]))
            .maybe_single()
            .execute()
        )
        if organiser is None or not _can_organise(service_client, organiser):
            raise AppError(
                code="organiser_unavailable",
                message="That organiser is not accepting requests",
                http_status=422,
                details={"message_key": "vendor.events.collab.errors.organiserUnavailable"},
            )

    return _act(request_id, "submit", current_user, service_client, extra_check=check)


def _organiser_still_eligible(service_client: ServiceRoleClient) -> Any:
    def check(_row: dict[str, Any], me: dict[str, Any]) -> None:
        _require_organiser_eligible(service_client, me)

    return check


@router.post("/requests/{request_id}/approve", response_model=RequestView)
async def approve_request(
    request_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    return _act(
        request_id,
        "approve",
        current_user,
        service_client,
        extra_check=_organiser_still_eligible(service_client),
    )


@router.post("/requests/{request_id}/decline", response_model=RequestView)
async def decline_request(
    request_id: str,
    body: ReasonBody,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    return _act(request_id, "decline", current_user, service_client, reason=body.reason)


@router.post("/requests/{request_id}/request-changes", response_model=RequestView)
async def request_changes(
    request_id: str,
    body: ReasonBody,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    return _act(request_id, "request_changes", current_user, service_client, reason=body.reason)


def _publish_guards(
    row: dict[str, Any], me: dict[str, Any], service_client: ServiceRoleClient
) -> str:
    """Organiser-account checks the normal publish route applies; returns a free slug."""
    from app.routers.organiser_events import _unique_event_slug
    from app.services.events.disputes_policy import UPHELD_SUSPENSION_THRESHOLD
    from app.services.events.high_value import (
        count_upheld_event_disputes,
        load_high_value_gmv_ngwee,
    )

    _require_organiser_eligible(service_client, me)
    if count_upheld_event_disputes(str(me["id"])) >= UPHELD_SUSPENSION_THRESHOLD:
        raise AppError(
            code="organiser_dispute_suspended",
            message="Ticketed publishing is suspended after three upheld event disputes",
            http_status=403,
            details={"message_key": "vendor.events.errors.disputeSuspended"},
        )
    draft, checklist, share = _stored_pieces(row)
    try:
        assert_submittable(draft, checklist, share, now=datetime.now(UTC))
    except AppError as exc:
        errors = exc.details.get("fields", [])
        if any(
            e.get("field") == "checklist.schedule.starts_at" and e.get("code") == "must_be_future"
            for e in errors
        ):
            raise AppError(
                code="past_instance",
                message="The event start time has already passed",
                http_status=422,
                details={"message_key": "vendor.events.errors.past_instance"},
            ) from exc
        raise
    paid = [t.price_ngwee for t in checklist.tiers if t.price_ngwee > 0]
    capacity = checklist.capacity.capacity or 0
    if paid and min(paid) * capacity >= load_high_value_gmv_ngwee():
        raise AppError(
            code="event_high_value_verification_required",
            message="Events projecting K100,000+ in ticket GMV need verification before publish",
            http_status=422,
            details={"message_key": "vendor.events.errors.highValueVerificationRequired"},
        )
    return str(_unique_event_slug(service_client, draft.title or "event"))


@router.post("/requests/{request_id}/publish", response_model=RequestView)
async def publish_request(
    request_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RequestView:
    return _act(
        request_id,
        "publish",
        current_user,
        service_client,
        extra_check=lambda row, me: _publish_guards(row, me, service_client),
    )
