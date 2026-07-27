"""M17-P02 — Cloudinary async transcode callback.

Cloudinary posts here when the eager 480p/720p MP4 + WebP poster are ready. The
posture matches the repo's other webhooks (`webhooks_lenco`, `webhooks_whatsapp`):

* verify the signature over the **raw body** with ``compare_digest``, **before**
  parsing anything;
* **fail closed** when the secret is unset — an unconfigured verifier must refuse,
  not wave callbacks through;
* dedupe on ``webhook_events (provider='cloudinary', event_id)`` so a replay is a
  no-op rather than a second transition.

The rule that shapes the rest of the module: **do not trust the callback's claims
where our own schema constrains them.** Cloudinary reports duration, formats and
derived URLs; we re-check duration against D-V3's 60s cap and require both
renditions plus a poster to actually be present. A mismatch is a **rejection**,
not a coercion — a clip that cannot be played at both ceilings has no business in
a data-capped feed.

This module cannot publish. Its only forward edge is ``screening →
pending_review``; a human does the rest in M17-P07.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Annotated, Any, Final, Protocol

from app.deps import get_supabase_client
from app.media.cloudinary_signing import MAX_CLIP_DURATION_S
from app.services.clips import screen, state_machine
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

PROVIDER: Final = "cloudinary"
WEBHOOK_EVENTS_TABLE: Final = "webhook_events"
CLIPS_TABLE: Final = "video_clips"

HEADER_SIGNATURE: Final = "X-Cld-Signature"
HEADER_TIMESTAMP: Final = "X-Cld-Timestamp"

MAX_BODY_BYTES: Final = 1_048_576

#: Both are required. A clip that only transcoded at one ceiling would force
#: cellular viewers onto the 720p rendition — precisely the data cost D-V2 exists
#: to prevent — so a partial result is a rejection, not a degraded publish.
REQUIRED_RENDITIONS: Final[tuple[str, ...]] = ("480p", "720p")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _verify_signature(raw_body: bytes, headers: Any, secret: str) -> bool:
    """Cloudinary's documented scheme: sha1(body + timestamp + secret)."""
    provided = (headers.get(HEADER_SIGNATURE) or "").strip()
    timestamp = (headers.get(HEADER_TIMESTAMP) or "").strip()
    if not provided or not timestamp:
        return False

    expected = hashlib.sha1(
        raw_body + timestamp.encode("utf-8") + secret.encode("utf-8")
    ).hexdigest()
    return hmac.compare_digest(expected, provided)


def _claim_event(service_client: ServiceRoleClient, event_id: str) -> bool:
    """Insert the dedupe row. False ⇒ already seen, so do nothing."""
    try:
        service_client.client.table(WEBHOOK_EVENTS_TABLE).insert(
            {"provider": PROVIDER, "event_id": event_id}
        ).execute()
    except Exception:
        # A unique violation is the expected replay path. Any other failure also
        # resolves to "do not process twice", which is the safe direction.
        return False
    return True


def _extract_renditions(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map Cloudinary's `eager` array onto our named ceilings.

    Keyed by the height we asked for rather than by array position: eager results
    are not order-guaranteed, and silently mislabelling 720p as 480p would send
    cellular viewers the big file.
    """
    eager = payload.get("eager")
    if not isinstance(eager, list):
        return {}

    found: dict[str, dict[str, Any]] = {}
    for entry in eager:
        if not isinstance(entry, dict):
            continue
        url = entry.get("secure_url") or entry.get("url")
        if not isinstance(url, str) or not url:
            continue
        width = entry.get("width")
        fmt = str(entry.get("format") or "").lower()
        if fmt == "webp":
            continue
        if width == 480:
            found["480p"] = {"url": url, "width": 480, "bytes": entry.get("bytes")}
        elif width == 720:
            found["720p"] = {"url": url, "width": 720, "bytes": entry.get("bytes")}
    return found


def _extract_poster(payload: dict[str, Any]) -> str | None:
    eager = payload.get("eager")
    if not isinstance(eager, list):
        return None
    for entry in eager:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("format") or "").lower() != "webp":
            continue
        url = entry.get("secure_url") or entry.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def _reject(
    service_client: ServiceRoleClient, *, clip_id: str, reason: str
) -> Response:
    """Refuse the clip through the guarded transition, so it is audited."""
    logger.info("clip transcode rejected", extra={"clip_id": clip_id, "reason": reason})
    try:
        state_machine.reject(service_client, clip_id=clip_id, reason=reason)
    except Exception:
        # Already terminal, or another writer moved it. The desired end state
        # (not advancing) holds either way.
        logger.info("clip reject skipped", extra={"clip_id": clip_id})
    return Response(status_code=200)


@router.post("/cloudinary")
async def receive_cloudinary_callback(
    request: Request,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Ingest one transcode-complete callback. Never publishes."""
    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_BYTES:
        return Response(status_code=413)

    # --- Gate 1: fail closed on an unset secret -----------------------------
    secret = settings.cloudinary_webhook_secret.strip()
    if not secret:
        logger.warning("cloudinary callback refused: signing secret is not configured")
        return Response(status_code=403)

    # --- Gate 2: signature over the raw bytes, before any parse -------------
    if not _verify_signature(raw_body, request.headers, secret):
        return Response(status_code=403)

    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400)
    if not isinstance(payload, dict):
        return Response(status_code=400)

    public_id = payload.get("public_id")
    if not isinstance(public_id, str) or not public_id.strip():
        return Response(status_code=400)

    # The public id is the clip id (set server-side at draft creation), so the
    # callback cannot name a clip the uploader did not own.
    clip_id = public_id.rsplit("/", 1)[-1].strip()

    clip_rows = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select("id, status, vendor_id, caption, duration_s")
        .eq("id", clip_id)
        .maybe_single()
        .execute()
    )
    if not clip_rows:
        # Unknown clip: 200 so Cloudinary stops retrying something we will never
        # accept, but nothing is created — a callback cannot conjure a clip.
        logger.info("cloudinary callback for unknown clip", extra={"clip_id": clip_id})
        return Response(status_code=200)
    clip = clip_rows[0]

    # --- Gate 3: replay dedupe, after auth + identification -----------------
    event_id = str(payload.get("notification_id") or payload.get("asset_id") or clip_id)
    if not _claim_event(service_client, event_id):
        return Response(status_code=200)

    status = str(clip.get("status") or "")
    if status != state_machine.SCREENING:
        # Out of order, or already handled. Safe to acknowledge and stop.
        logger.info(
            "cloudinary callback ignored for non-screening clip",
            extra={"clip_id": clip_id, "status": status},
        )
        return Response(status_code=200)

    # --- Validate the reported media against OUR constraints ----------------
    reported_duration = payload.get("duration")
    if isinstance(reported_duration, (int, float)):
        if reported_duration > MAX_CLIP_DURATION_S:
            return _reject(service_client, clip_id=clip_id, reason="duration_exceeded")
    else:
        reported_duration = None

    renditions = _extract_renditions(payload)
    missing = [name for name in REQUIRED_RENDITIONS if name not in renditions]
    if missing:
        return _reject(service_client, clip_id=clip_id, reason="missing_renditions")

    poster_url = _extract_poster(payload)
    if not poster_url:
        return _reject(service_client, clip_id=clip_id, reason="missing_poster")

    patch: dict[str, Any] = {
        "renditions": renditions,
        "poster_url": poster_url,
        "cloudinary_public_id": public_id,
    }
    if reported_duration is not None:
        patch["duration_s"] = int(reported_duration)

    service_client.client.table(CLIPS_TABLE).update(patch).eq("id", clip_id).execute()

    # --- Automated screen decides the next state (never `published`) --------
    screen.apply_screen(
        service_client,
        clip_id=clip_id,
        caption=clip.get("caption"),
        category_name=None,
    )
    return Response(status_code=200)
