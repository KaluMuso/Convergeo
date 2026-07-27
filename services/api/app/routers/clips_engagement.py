"""M17-P03 — likes, comments, reports and view counting.

Every write here is **idempotent by constraint, not by application logic**. The
schema from M17-P01 does the deduping:

* ``clip_likes`` PK ``(clip_id, user_id)`` — a double-like cannot create a second row;
* ``clip_reports`` UNIQUE ``(clip_id, reporter_id)`` — one report per person per clip;
* ``clip_views`` UNIQUE ``(clip_id, user_id, viewed_on)`` — one view per person per day.

That distinction matters under concurrency. A read-then-write ("do they already
like it? no → insert, bump") loses races: two simultaneous taps both read "no" and
both bump. Here the insert is attempted unconditionally and **the counter moves
only if the insert actually created a row** — so the database, not the request
ordering, decides how many times the counter moves.

Counters are never written directly. They move through
``state_machine.bump_counter`` → the ``SECURITY DEFINER`` ``clip_bump_counter``
function, which is the only privilege in the system that can touch those columns
(migration ``0076`` grants clients column-level UPDATE on metadata only). A request
body that tries to set a counter is rejected by ``StrictModel``'s ``extra=forbid``
before it reaches any of this.

**View counting does not trust the client.** A client claiming three seconds is how
you *qualify* for a view, not how you *get* one: the per-user-per-day unique key is
what bounds the count, so a script claiming 3 s a thousand times still produces one
row and one increment.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated, Any, Final, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.analytics import events as analytics_events
from app.services.clips import flags, screen, state_machine
from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clips", tags=["clips"])

CLIPS_TABLE: Final = "video_clips"
LIKES_TABLE: Final = "clip_likes"
COMMENTS_TABLE: Final = "clip_comments"
REPORTS_TABLE: Final = "clip_reports"
VIEWS_TABLE: Final = "clip_views"

#: D-V1: a view is three seconds of actual watching, not an impression. Below this
#: the feed's autoplay-adjacent scroll-past would inflate every number it touches.
MIN_VIEW_MS: Final = 3_000

MAX_COMMENT_LEN: Final = 500
COMMENT_PAGE_SIZE: Final = 50

#: Comments are the only free-text surface here, so they get the tightest ceiling.
COMMENT_RATE_LIMIT: Final = 10
ENGAGEMENT_RATE_LIMIT: Final = 60
REPORT_RATE_LIMIT: Final = 20


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ----------------------------------------------------------------
class LikeResponse(StrictModel):
    clip_id: str
    liked: bool
    like_count: int


class CommentCreateRequest(StrictModel):
    body: str = Field(min_length=1, max_length=MAX_COMMENT_LEN)


class CommentOut(StrictModel):
    id: str
    clip_id: str
    author_id: str
    body: str
    created_at: str | None


class CommentListResponse(StrictModel):
    items: list[CommentOut]
    comment_count: int


class ReportCreateRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=500)


class ReportResponse(StrictModel):
    clip_id: str
    reported: bool


class ViewRequest(StrictModel):
    #: Milliseconds actually watched, as measured by the player. Untrusted — it
    #: gates eligibility only; the unique key bounds the count.
    watched_ms: int = Field(ge=0)


class ViewResponse(StrictModel):
    clip_id: str
    counted: bool
    view_count: int | None = None


# --- Helpers ----------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


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
            message_key="clips.errors.rateLimited",
            message="Too many clip requests",
        )


def _not_found(clip_id: str) -> AppError:
    return AppError(
        code="not_found",
        message="Clip not found",
        http_status=404,
        details={"clip_id": clip_id},
    )


def _load_published_clip(
    service_client: ServiceRoleClient, clip_id: str
) -> dict[str, Any]:
    """Engagement targets a *published* clip or nothing.

    Same 404 for "no such clip" and "not published": a distinct status would let
    anyone confirm that an unpublished clip id exists, which is the only thing an
    id-guessing probe is after.
    """
    rows = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select("id, status, vendor_id, like_count, comment_count, view_count")
        .eq("id", clip_id)
        .maybe_single()
        .execute()
    )
    if not rows or str(rows[0].get("status")) != state_machine.PUBLISHED:
        raise _not_found(clip_id)
    return rows[0]


def _insert_once(service_client: ServiceRoleClient, table: str, row: dict[str, Any]) -> bool:
    """Insert, returning whether this call is the one that created the row.

    ``False`` means the unique key rejected it — i.e. the row was already there,
    which is precisely the idempotent case. No pre-read, so two concurrent callers
    cannot both conclude "not there yet".
    """
    try:
        response = service_client.client.table(table).insert(row).execute()
    except Exception:
        return False
    return bool(_rows(response)) or getattr(response, "data", None) is not None


def _emit(event_type: str, *, clip_id: str, user_id: str | None) -> None:
    """Fire-and-forget analytics. Never allowed to fail an engagement write."""
    try:
        analytics_events.record_event(
            event_type=event_type,
            user_id=user_id,
            entity_type="video_clip",
            entity_id=clip_id,
        )
    except Exception:
        logger.debug("clip analytics emit skipped", extra={"event_type": event_type})


# --- Likes ------------------------------------------------------------------
@router.post("/{clip_id}/like", response_model=LikeResponse)
async def like_clip(
    clip_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> LikeResponse:
    """Like a clip. Liking twice is a success that changes nothing."""
    clip = _load_published_clip(service_client, clip_id)
    _rate_limit(
        service_client,
        scope="clip_like",
        key=current_user.id,
        limit=ENGAGEMENT_RATE_LIMIT,
    )

    created = _insert_once(
        service_client, LIKES_TABLE, {"clip_id": clip_id, "user_id": current_user.id}
    )
    if not created:
        # Already liked. Report the current count rather than re-bumping.
        return LikeResponse(
            clip_id=clip_id, liked=True, like_count=int(clip.get("like_count") or 0)
        )

    count = state_machine.bump_counter(
        service_client, clip_id=clip_id, column=state_machine.LIKE_COUNT, delta=1
    )
    _emit("clip_like", clip_id=clip_id, user_id=current_user.id)
    return LikeResponse(clip_id=clip_id, liked=True, like_count=count)


@router.delete("/{clip_id}/like", response_model=LikeResponse)
async def unlike_clip(
    clip_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> LikeResponse:
    """Remove a like. Removing a like that is not there is also a success."""
    clip = _load_published_clip(service_client, clip_id)
    _rate_limit(
        service_client,
        scope="clip_like",
        key=current_user.id,
        limit=ENGAGEMENT_RATE_LIMIT,
    )

    removed = _rows(
        service_client.client.table(LIKES_TABLE)
        .delete()
        .eq("clip_id", clip_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not removed:
        return LikeResponse(
            clip_id=clip_id, liked=False, like_count=int(clip.get("like_count") or 0)
        )

    count = state_machine.bump_counter(
        service_client, clip_id=clip_id, column=state_machine.LIKE_COUNT, delta=-1
    )
    return LikeResponse(clip_id=clip_id, liked=False, like_count=count)


# --- Comments ---------------------------------------------------------------
def _require_comments_enabled(service_client: ServiceRoleClient) -> None:
    """F-V2 gate. Built, but OFF until the founder flips ``clips_comments``."""
    if not flags.comments_enabled(service_client):
        raise AppError(
            code="clip_comments_disabled",
            message="Comments are not available",
            http_status=404,
        )


@router.get("/{clip_id}/comments", response_model=CommentListResponse)
async def list_clip_comments(
    clip_id: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=COMMENT_PAGE_SIZE)] = COMMENT_PAGE_SIZE,
) -> CommentListResponse:
    _require_comments_enabled(service_client)
    clip = _load_published_clip(service_client, clip_id)

    rows = _rows(
        service_client.client.table(COMMENTS_TABLE)
        .select("id, clip_id, author_id, body, created_at, status")
        .eq("clip_id", clip_id)
        .eq("status", "visible")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return CommentListResponse(
        items=[
            CommentOut(
                id=str(row["id"]),
                clip_id=clip_id,
                author_id=str(row.get("author_id") or ""),
                body=str(row.get("body") or ""),
                created_at=str(row["created_at"]) if row.get("created_at") else None,
            )
            for row in rows
            # Belt and braces: hidden comments are excluded by the query above and
            # again here, so a driver that ignores a filter cannot leak one.
            if str(row.get("status", "visible")) == "visible"
        ],
        comment_count=int(clip.get("comment_count") or 0),
    )


@router.post("/{clip_id}/comments", response_model=CommentOut, status_code=201)
async def create_clip_comment(
    clip_id: str,
    body: CommentCreateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CommentOut:
    """Post a comment: gated, rate-limited, then screened — in that order.

    Screening happens **before** persistence, so prohibited text is never stored
    and then hidden; it is simply never written.
    """
    _require_comments_enabled(service_client)
    _load_published_clip(service_client, clip_id)
    _rate_limit(
        service_client,
        scope="clip_comment",
        key=current_user.id,
        limit=COMMENT_RATE_LIMIT,
    )

    text = body.body.strip()
    if not text:
        raise AppError(
            code="invalid_comment",
            message="Comment cannot be empty",
            http_status=422,
        )

    verdict = screen.screen_text(text)
    if not verdict.allowed:
        # Classification only in the log — the text is untrusted and may be
        # adversarial, and the reason is what an operator actually needs.
        logger.info(
            "clip comment rejected by screen",
            extra={"clip_id": clip_id, "reason": verdict.reason},
        )
        raise AppError(
            code="prohibited_comment",
            message="Comment cannot be posted",
            http_status=422,
            details={"reason": verdict.reason},
        )

    inserted = _rows(
        service_client.client.table(COMMENTS_TABLE)
        .insert({"clip_id": clip_id, "author_id": current_user.id, "body": text})
        .execute()
    )
    if not inserted:
        raise AppError(
            code="comment_failed",
            message="Comment could not be saved",
            http_status=500,
        )

    state_machine.bump_counter(
        service_client, clip_id=clip_id, column=state_machine.COMMENT_COUNT, delta=1
    )
    row = inserted[0]
    return CommentOut(
        id=str(row.get("id") or ""),
        clip_id=clip_id,
        author_id=current_user.id,
        body=text,
        created_at=str(row["created_at"]) if row.get("created_at") else None,
    )


# --- Reports ----------------------------------------------------------------
@router.post("/{clip_id}/report", response_model=ReportResponse)
async def report_clip(
    clip_id: str,
    body: ReportCreateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ReportResponse:
    """Report a clip for review (feeds M17-P07's queue).

    Reporting twice is a no-op, not an error: a user who taps again because the
    clip is still up should not be told off, and the moderation queue should not
    show one clip ten times because one person was persistent.
    """
    _load_published_clip(service_client, clip_id)
    _rate_limit(
        service_client,
        scope="clip_report",
        key=current_user.id,
        limit=REPORT_RATE_LIMIT,
    )

    _insert_once(
        service_client,
        REPORTS_TABLE,
        {
            "clip_id": clip_id,
            "reporter_id": current_user.id,
            "reason": body.reason.strip()[:500],
        },
    )
    # Same answer either way — whether this was the first report is not the
    # reporter's business, and telling them would leak others' reports.
    return ReportResponse(clip_id=clip_id, reported=True)


# --- Views ------------------------------------------------------------------
@router.post("/{clip_id}/view", response_model=ViewResponse)
async def record_clip_view(
    clip_id: str,
    body: ViewRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    response: Response,
) -> ViewResponse:
    """Count a view, at most once per user per day.

    Anonymous viewers are **not counted**. The alternative — a client-supplied
    "stable non-PII key" — is a counter increment the client controls, and D-V5's
    honesty about numbers is worth more than a bigger view count.
    """
    clip = _load_published_clip(service_client, clip_id)
    _rate_limit(
        service_client,
        scope="clip_view",
        key=current_user.id,
        limit=ENGAGEMENT_RATE_LIMIT,
    )

    if body.watched_ms < MIN_VIEW_MS:
        # Not an error: a scroll-past is a normal thing to report honestly.
        response.status_code = 202
        return ViewResponse(
            clip_id=clip_id, counted=False, view_count=int(clip.get("view_count") or 0)
        )

    # `viewed_on` is left to the column default (UTC date) rather than sent from
    # here, so a client cannot pick yesterday's date to earn a second view.
    created = _insert_once(
        service_client, VIEWS_TABLE, {"clip_id": clip_id, "user_id": current_user.id}
    )
    if not created:
        return ViewResponse(
            clip_id=clip_id, counted=False, view_count=int(clip.get("view_count") or 0)
        )

    count = state_machine.bump_counter(
        service_client, clip_id=clip_id, column=state_machine.VIEW_COUNT, delta=1
    )
    _emit("clip_view", clip_id=clip_id, user_id=current_user.id)
    return ViewResponse(clip_id=clip_id, counted=True, view_count=count)
