"""M18-P02 — WAHA provider normaliser (pinned contract: WAHA ``2026.5.1``).

Pure and I/O-free: it turns WAHA's payload shape into an internal strict model
and nothing else. No network, no database, no side effects.

Everything crossing this boundary is **untrusted data**. Captions, filenames,
declared MIME types, and media URLs are carried as opaque strings for M18-P03 to
verify — this module never trusts, resolves, or fetches any of them.

The contract is pinned: only the documented session ``message`` event and its
signed envelope are accepted. An algorithm, header, or event-shape change needs
an ADR and a test update, not a silent edit here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

# Pinned WAHA protocol version this normaliser understands.
WAHA_CONTRACT_VERSION: Final = "2026.5.1"

# The only event we accept. Anything else is ignored safely.
EVENT_MESSAGE: Final = "message"

# WhatsApp JID suffixes. Only the individual-chat suffix may ever be processed.
JID_INDIVIDUAL_SUFFIX: Final = "@c.us"
JID_GROUP_SUFFIX: Final = "@g.us"
JID_BROADCAST_SUFFIX: Final = "@broadcast"
JID_NEWSLETTER_SUFFIX: Final = "@newsletter"

# Suffixes that are categorically forbidden (D35 §4.3).
FORBIDDEN_JID_SUFFIXES: Final[tuple[str, ...]] = (
    JID_GROUP_SUFFIX,
    JID_BROADCAST_SUFFIX,
    JID_NEWSLETTER_SUFFIX,
)

_STATUS_JIDS: Final[frozenset[str]] = frozenset({"status@broadcast"})

_MSISDN_FROM_JID = re.compile(r"^(\d{6,15})@")


class NormalisationError(ValueError):
    """The payload does not match the pinned WAHA contract."""


@dataclass(frozen=True, slots=True)
class NormalisedEvent:
    """A structurally valid inbound WAHA message event.

    Construction implies the payload *parsed*; it implies nothing about whether
    the sender is authorised. Eligibility is decided later, by the session
    service.
    """

    event_id: str
    session: str
    chat_jid: str
    sender_msisdn_raw: str
    text: str | None
    media_refs: tuple[dict[str, Any], ...] = field(default=())

    @property
    def is_group_like(self) -> bool:
        """True for any group, broadcast, status, or channel conversation."""
        jid = self.chat_jid.lower()
        if jid in _STATUS_JIDS:
            return True
        return any(jid.endswith(suffix) for suffix in FORBIDDEN_JID_SUFFIXES)

    @property
    def is_individual_chat(self) -> bool:
        """True only for a genuine 1:1 chat — the whitelist, not the blacklist.

        Deliberately positive: a JID shape we have never seen is *not* an
        individual chat, so a future WhatsApp conversation type cannot slip
        through by simply not matching the forbidden list.
        """
        return self.chat_jid.lower().endswith(JID_INDIVIDUAL_SUFFIX) and not self.is_group_like

    @property
    def kind(self) -> str:
        if self.media_refs and self.text:
            return "mixed"
        if self.media_refs:
            return "image"
        if self.text:
            return "text"
        return "unsupported"


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NormalisationError(f"missing or invalid field: {key}")
    return value.strip()


def extract_msisdn(jid: str) -> str:
    """Pull the raw digits out of a JID. Returns '' when the shape is unknown."""
    match = _MSISDN_FROM_JID.match(jid)
    return match.group(1) if match else ""


def normalise(payload: Any) -> NormalisedEvent:
    """Normalise a WAHA webhook body into :class:`NormalisedEvent`.

    Raises :class:`NormalisationError` for anything that is not a well-formed
    session ``message`` event on the pinned contract.
    """
    if not isinstance(payload, dict):
        raise NormalisationError("payload must be an object")

    event = payload.get("event")
    if event != EVENT_MESSAGE:
        raise NormalisationError(f"unsupported event: {event!r}")

    session = _require_str(payload, "session")

    body = payload.get("payload")
    if not isinstance(body, dict):
        raise NormalisationError("missing message payload")

    event_id = _require_str(body, "id")

    # WAHA reports the conversation on `from`; a 1:1 chat carries the sender's
    # own JID, a group carries the group JID with `participant` set.
    chat_jid = _require_str(body, "from")

    # `fromMe` messages are our own echoes and must never create intake.
    if bool(body.get("fromMe", False)):
        raise NormalisationError("outbound echo is not intake")

    # In a group WAHA sets `participant`; its presence alone is a strong group
    # signal even if the JID suffix were somehow unfamiliar.
    participant = body.get("participant")
    if isinstance(participant, str) and participant.strip():
        # Keep the group JID as the chat so the caller audits dropped_group.
        chat_jid = chat_jid

    sender_raw = extract_msisdn(chat_jid)

    text_value = body.get("body")
    text = text_value.strip() if isinstance(text_value, str) and text_value.strip() else None

    media_refs: list[dict[str, Any]] = []
    media = body.get("media")
    if isinstance(media, dict):
        media_refs.append(_opaque_media(media))
    elif isinstance(media, list):
        for item in media:
            if isinstance(item, dict):
                media_refs.append(_opaque_media(item))

    return NormalisedEvent(
        event_id=event_id,
        session=session,
        chat_jid=chat_jid,
        sender_msisdn_raw=sender_raw,
        text=text,
        media_refs=tuple(media_refs),
    )


def _opaque_media(item: dict[str, Any]) -> dict[str, Any]:
    """Carry media hints forward WITHOUT trusting any of them.

    The url, mimetype, and filename are attacker-controlled. M18-P03 fetches
    server-side and verifies magic bytes; nothing here may be treated as fact.
    """
    return {
        "url": item.get("url") if isinstance(item.get("url"), str) else None,
        "declared_mimetype": item.get("mimetype")
        if isinstance(item.get("mimetype"), str)
        else None,
        "declared_filename": item.get("filename")
        if isinstance(item.get("filename"), str)
        else None,
    }
