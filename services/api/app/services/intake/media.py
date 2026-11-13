"""M18-P03 — safe media quarantine for WAHA intake (D35).

Inbound images are fetched **server-side** through short-lived provider
credentials, verified, deduped, and stored **privately** until a human reviews
them. Nothing here ever attaches media to a public listing or mints a public URL.

The trust posture, in order of application:

1. Fetch with a hard timeout and a **capped streaming read**, so an enormous or
   never-ending response cannot exhaust memory.
2. Verify **magic bytes** and a header-derived **pixel budget** — never the
   declared MIME type or filename, both of which the sender controls.
3. Run the **quarantine hook**; a non-clean verdict rejects.
4. **Strip EXIF** on the persisted copy (it carries GPS and can carry text that
   M18-P04 must never treat as instructions).
5. Dedupe by **content hash** so a repeat within a session stores one object.

Every failure is recoverable: the session lands in ``needs_details`` via P01's
guarded transition, never a half-attached draft and never a crash.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Protocol

import httpx
from app.services.intake import config as intake_config
from app.services.intake import imagecheck, state_machine

logger = logging.getLogger(__name__)

BUCKET: Final = "vendor-intake-media"
MEDIA_TABLE: Final = "intake_media"

# Limits. Deliberately modest: these are phone photos of products.
MAX_IMAGE_BYTES: Final = 8 * 1024 * 1024
MAX_DIMENSION: Final = 12_000
MAX_PIXELS: Final = 40_000_000
MAX_IMAGES_PER_SESSION: Final = 8  # mirrors the listing_images cap
FETCH_TIMEOUT_SECONDS: Final = 15.0
CHUNK_BYTES: Final = 64 * 1024


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class MediaRejected(Exception):
    """A media item could not be safely ingested. Carries a stable reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class StoredMedia:
    storage_path: str
    content_hash: str
    mime_type: str
    byte_size: int
    width: int
    height: int


# --- Quarantine seam --------------------------------------------------------
# The operator wires a real scanner here at Stage 1 (waha-vendor-intake.md §10).
# The default is permissive-but-real: it is called on every item, its verdict is
# honoured, and a scanner can be substituted without touching this module.
QuarantineHook = Callable[[bytes], bool]


def _default_quarantine_hook(_data: bytes) -> bool:
    """Return True when the payload is considered clean."""
    return True


_quarantine_hook: QuarantineHook = _default_quarantine_hook


def set_quarantine_hook(hook: QuarantineHook) -> None:
    """Install the malware/quarantine checker used before any object is stored."""
    global _quarantine_hook
    _quarantine_hook = hook


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def strip_exif(data: bytes, mime_type: str) -> bytes:
    """Remove EXIF/metadata segments without re-encoding pixel data.

    For JPEG this drops APP1 (EXIF/XMP) and APP2..APP15 segments, which is where
    GPS coordinates and injected text live. PNG and WebP are passed through: we
    do not carry their ancillary metadata into any prompt, and rewriting their
    chunk structure risks corrupting an otherwise valid image.
    """
    if mime_type != imagecheck.JPEG:
        return data

    out = bytearray(data[:2])  # SOI
    index = 2
    length = len(data)
    while index + 3 < length:
        if data[index] != 0xFF:
            # Malformed beyond the header check; return what we have verified.
            return bytes(data)
        marker = data[index + 1]
        if marker == 0xDA:  # Start of scan — copy the remainder verbatim.
            out.extend(data[index:])
            return bytes(out)
        segment_length = int.from_bytes(data[index + 2 : index + 4], "big")
        if segment_length < 2:
            return bytes(data)
        segment_end = index + 2 + segment_length
        # APP1..APP15 carry EXIF/XMP/etc. APP0 (JFIF) is structural, keep it.
        if 0xE1 <= marker <= 0xEF:
            index = segment_end
            continue
        out.extend(data[index:segment_end])
        index = segment_end
    return bytes(out)


async def _fetch(url: str) -> bytes:
    """Fetch server-side with a timeout and a hard byte ceiling."""
    headers = {"Authorization": f"Bearer {intake_config.api_key()}"}
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    raise MediaRejected("fetch_failed")
                buffer = bytearray()
                async for chunk in response.aiter_bytes(CHUNK_BYTES):
                    buffer.extend(chunk)
                    if len(buffer) > MAX_IMAGE_BYTES:
                        # Stop reading rather than buffering an unbounded body.
                        raise MediaRejected("too_large")
                return bytes(buffer)
    except MediaRejected:
        raise
    except httpx.TimeoutException as exc:
        raise MediaRejected("fetch_timeout") from exc
    except httpx.HTTPError as exc:
        raise MediaRejected("fetch_failed") from exc


def _existing(
    service_client: ServiceRoleClient, session_id: str, content_hash: str
) -> dict[str, Any] | None:
    response = (
        service_client.client.table(MEDIA_TABLE)
        .select("*")
        .eq("session_id", session_id)
        .eq("content_hash", content_hash)
        .maybe_single()
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def _count(service_client: ServiceRoleClient, session_id: str) -> int:
    response = (
        service_client.client.table(MEDIA_TABLE)
        .select("id")
        .eq("session_id", session_id)
        .execute()
    )
    return len(_rows(response))


async def ingest_one(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    session_id: str,
    media_ref: dict[str, Any],
) -> StoredMedia:
    """Fetch, verify, quarantine-check, strip, dedupe, and store one image.

    Raises :class:`MediaRejected` with a stable reason on any failure; the
    caller turns that into a recoverable ``needs_details``.
    """
    url = media_ref.get("url")
    if not isinstance(url, str) or not url.strip():
        raise MediaRejected("missing_url")

    if _count(service_client, session_id) >= MAX_IMAGES_PER_SESSION:
        raise MediaRejected("too_many_images")

    data = await _fetch(url)

    # Verify against reality, not against what the sender declared. The declared
    # mimetype/filename in media_ref are deliberately never consulted.
    try:
        facts = imagecheck.verify(
            data,
            max_bytes=MAX_IMAGE_BYTES,
            max_dimension=MAX_DIMENSION,
            max_pixels=MAX_PIXELS,
        )
    except imagecheck.ImageRejected as exc:
        raise MediaRejected(exc.reason) from exc

    if not _quarantine_hook(data):
        raise MediaRejected("quarantine_flagged")

    cleaned = strip_exif(data, facts.mime_type)
    content_hash = hashlib.sha256(cleaned).hexdigest()

    duplicate = _existing(service_client, session_id, content_hash)
    if duplicate is not None:
        return StoredMedia(
            storage_path=str(duplicate["storage_path"]),
            content_hash=content_hash,
            mime_type=str(duplicate["mime_type"]),
            byte_size=int(duplicate["byte_size"]),
            width=int(duplicate.get("width_px") or facts.width),
            height=int(duplicate.get("height_px") or facts.height),
        )

    storage_path = f"intake/{vendor_id}/{session_id}/{content_hash}"
    try:
        service_client.client.storage.from_(BUCKET).upload(
            storage_path,
            cleaned,
            {"content-type": facts.mime_type, "upsert": "true"},
        )
    except Exception as exc:
        raise MediaRejected("storage_failed") from exc

    service_client.client.table(MEDIA_TABLE).insert(
        {
            "session_id": session_id,
            "storage_path": storage_path,
            "content_hash": content_hash,
            "byte_size": len(cleaned),
            "mime_type": facts.mime_type,
            "width_px": facts.width,
            "height_px": facts.height,
        }
    ).execute()

    return StoredMedia(
        storage_path=storage_path,
        content_hash=content_hash,
        mime_type=facts.mime_type,
        byte_size=len(cleaned),
        width=facts.width,
        height=facts.height,
    )


async def ingest_session_media(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    session_id: str,
    media_refs: list[dict[str, Any]],
) -> list[StoredMedia]:
    """Ingest every media ref, failing **closed but recoverable**.

    On any rejection the session is moved to ``needs_details`` with a stable
    reason so the vendor can retry — never a half-attached draft, never a crash.
    """
    stored: list[StoredMedia] = []
    for ref in media_refs:
        try:
            stored.append(
                await ingest_one(
                    service_client,
                    vendor_id=vendor_id,
                    session_id=session_id,
                    media_ref=ref,
                )
            )
        except MediaRejected as exc:
            logger.info("intake media rejected", extra={"reason": exc.reason})
            _fail_soft(service_client, session_id=session_id, reason=exc.reason)
            return stored
    return stored


def _fail_soft(service_client: ServiceRoleClient, *, session_id: str, reason: str) -> None:
    """Move the session to needs_details, tolerating an already-there state."""
    try:
        state_machine.transition(
            service_client,
            session_id=session_id,
            to_status=state_machine.NEEDS_DETAILS,
            extra={"pending_requests": [{"key": "intake.media_failed", "reason": reason}]},
        )
    except Exception:
        # Already in needs_details (or terminal) — the recoverable state is what
        # matters, not winning the transition race.
        logger.info("intake media fail-soft transition skipped")
