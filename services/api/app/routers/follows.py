"""R02-P14b — vendor follows: a commerce subscription, not a social graph (D37).

A follow means "tell me when this shop lists something new" — never a visible
edge between people. D37 forbids public profiles and social graphs, so this
router deliberately exposes:

* NO public follower count — only the vendor's owner (or an admin) may read
  even the aggregate, and only through the ``SECURITY DEFINER``
  ``vendor_follower_count`` function from migration 0083, which re-checks
  ownership inside the database;
* NO follower list endpoint at all — the identities behind the count are not
  readable by anyone, including the vendor being followed. Under the Zambia
  DPA, "this shop knows you follow it" is a disclosure nobody consented to.

Idempotency is the primary key's job (0083): the insert is attempted
unconditionally and the ``(user_id, vendor_id)`` PK absorbs a double-tap.
A read-then-write would race on exactly the double-tap it is meant to handle.

Following an inactive vendor answers the same 404 as a vendor id that never
existed — a distinct status would let anyone probe whether a suspended vendor
id is real, which is the only thing an id-guessing probe is after.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Final, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import POLICIES, RateLimitPolicy, route_id
from app.core.supabase import get_user_client
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Query, Response

router = APIRouter(tags=["follows"])

FOLLOWS_TABLE: Final = "vendor_follows"
VENDORS_TABLE: Final = "vendors"

#: Postgres unique-violation SQLSTATE — the PK doing the idempotency work.
UNIQUE_VIOLATION: Final = "23505"

DEFAULT_PAGE_SIZE: Final = 20
MAX_PAGE_SIZE: Final = 50

#: Following is a rare, deliberate human action; 60/hour absorbs any honest
#: browsing session while making follow-graph scraping-by-probing expensive.
FOLLOW_WRITE_LIMIT: Final = 60
FOLLOW_WRITE_WINDOW: Final = timedelta(hours=1)

# Declarative registry entries for the startup coverage gate. Registered here
# rather than in app/core/ratelimit_policies.py only because this pebble owns
# exactly this file; ``discover_routers`` imports every router module before
# ``assert_all_mutating_routes_covered`` runs, so these land in POLICIES in
# time. Fold into the registry file on the next touch of that file.
FOLLOW_WRITE: Final = RateLimitPolicy(
    scope="vendor_follow", limit=FOLLOW_WRITE_LIMIT, window=FOLLOW_WRITE_WINDOW
)
POLICIES.setdefault(route_id("PUT", "/vendors/{vendor_id}/follow"), FOLLOW_WRITE)
POLICIES.setdefault(route_id("DELETE", "/vendors/{vendor_id}/follow"), FOLLOW_WRITE)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ------------------------------------------------------------------
class FollowedVendor(StrictModel):
    vendor_id: str
    name: str
    slug: str
    followed_at: str | None = None


class FollowListResponse(StrictModel):
    items: list[FollowedVendor]
    limit: int
    offset: int


class FollowerCountResponse(StrictModel):
    #: The aggregate is all a vendor ever learns about their followers (D37).
    count: int


# --- Helpers ------------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _vendor_not_found() -> AppError:
    """The one 404 for every way a vendor can fail to be followable.

    Deliberately carries no details: the error for an inactive vendor must be
    byte-identical to the one for an id that never existed, so the endpoint
    cannot be used as an existence oracle for suspended vendors.
    """
    return AppError(code="not_found", message="Vendor not found", http_status=404)


def _require_active_vendor(service_client: ServiceRoleClient, vendor_id: str) -> None:
    rows = _rows(
        service_client.client.table(VENDORS_TABLE)
        .select("id")
        .eq("id", vendor_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not rows:
        raise _vendor_not_found()


def _rate_limit_follow(service_client: ServiceRoleClient, user_id: str) -> None:
    """Follow and unfollow share one budget — a follow/unfollow flip-flop loop
    is the same abuse either way round."""
    allowed, retry_after = bump_rate_counter(
        scope="vendor_follow",
        key=user_id,
        window=FOLLOW_WRITE_WINDOW,
        limit=FOLLOW_WRITE_LIMIT,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="follows.errors.rateLimited",
            message="Too many follow requests",
        )


# --- Endpoints ------------------------------------------------------------------
@router.put("/vendors/{vendor_id}/follow", status_code=204)
async def follow_vendor(
    vendor_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> Response:
    """Follow a vendor. Following twice is a success that changes nothing."""
    _require_active_vendor(service_client, vendor_id)
    _rate_limit_follow(service_client, current_user.id)

    try:
        service_client.client.table(FOLLOWS_TABLE).insert(
            {"user_id": current_user.id, "vendor_id": vendor_id}
        ).execute()
    except Exception as exc:
        if getattr(exc, "code", None) != UNIQUE_VIOLATION:
            raise
        # Already following: the PK absorbed the double-tap. 204 both times —
        # idempotency by constraint, not by application logic (0083).

    # Seam: the new-listing notification to followers is a separate pebble; it
    # will consume vendor_follows — nothing is emitted on the follow itself.
    return Response(status_code=204)


@router.delete("/vendors/{vendor_id}/follow", status_code=204)
async def unfollow_vendor(
    vendor_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> Response:
    """Unfollow a vendor. Unfollowing something never followed is also 204.

    No vendor lookup on purpose: deleting zero rows is the idempotent success
    case, and answering 404 for an unknown vendor id here would reopen the
    existence oracle the PUT closes.
    """
    _rate_limit_follow(service_client, current_user.id)

    service_client.client.table(FOLLOWS_TABLE).delete().eq("user_id", current_user.id).eq(
        "vendor_id", vendor_id
    ).execute()
    return Response(status_code=204)


@router.get("/me/follows", response_model=FollowListResponse)
async def list_my_follows(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FollowListResponse:
    """The caller's own followed vendors — the only follow list that exists."""
    follow_rows = _rows(
        service_client.client.table(FOLLOWS_TABLE)
        .select("vendor_id, created_at")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
        .execute()
    )

    vendor_ids = [str(row["vendor_id"]) for row in follow_rows if row.get("vendor_id")]
    vendors_by_id: dict[str, dict[str, Any]] = {}
    if vendor_ids:
        vendor_rows = _rows(
            service_client.client.table(VENDORS_TABLE)
            .select("id, display_name, slug, status")
            .in_("id", vendor_ids)
            .execute()
        )
        vendors_by_id = {
            str(row["id"]): row
            for row in vendor_rows
            # A vendor suspended after being followed simply drops out of the
            # list — same no-oracle rule as the 404 on follow: no "suspended"
            # label that would disclose lifecycle state.
            if str(row.get("status")) == "active"
        }

    items: list[FollowedVendor] = []
    for row in follow_rows:
        vendor = vendors_by_id.get(str(row.get("vendor_id")))
        if vendor is None:
            continue
        items.append(
            FollowedVendor(
                vendor_id=str(vendor["id"]),
                name=str(vendor.get("display_name") or ""),
                slug=str(vendor.get("slug") or ""),
                followed_at=str(row["created_at"]) if row.get("created_at") else None,
            )
        )
    return FollowListResponse(items=items, limit=limit, offset=offset)


@router.get("/vendor/followers/count", response_model=FollowerCountResponse)
async def my_follower_count(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FollowerCountResponse:
    """Aggregate follower count for the vendor the caller owns.

    Owner-only, and an aggregate only — there is deliberately NO public
    follower count and NO follower list endpoint anywhere: D37 forbids public
    profiles and social graphs, so a follow is a commerce subscription and the
    count is a private business metric, not a vanity number.

    Everything runs on the caller's own client: RLS resolves the vendor via
    ``vendors.owner_user_id``, and ``vendor_follower_count`` is SECURITY
    DEFINER with its own owner/admin check, so the database re-enforces both
    steps even if this router is bypassed.
    """
    user_client = get_user_client(current_user.token, settings)

    vendor_rows = _rows(
        user_client.table(VENDORS_TABLE)
        .select("id")
        .eq("owner_user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if not vendor_rows:
        # Same 404 shape as an unknown vendor: a non-vendor caller learns
        # nothing here beyond "there is nothing for you".
        raise _vendor_not_found()

    vendor_id = str(vendor_rows[0]["id"])
    response = user_client.rpc("vendor_follower_count", {"p_vendor_id": vendor_id}).execute()

    data = getattr(response, "data", None)
    if isinstance(data, bool):
        raise AppError(
            code="internal_error",
            message="Unexpected follower count response",
            http_status=500,
        )
    if isinstance(data, int):
        count = data
    elif isinstance(data, list) and data and isinstance(data[0], int):
        count = data[0]
    else:
        raise AppError(
            code="internal_error",
            message="Unexpected follower count response",
            http_status=500,
        )
    return FollowerCountResponse(count=count)
