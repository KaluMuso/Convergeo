"""Build the live channel-adapter map, defensively.

WhatsApp is always constructed (its adapter resolves env lazily at send-time and
never raises on construction). SMS/email builders read required env eagerly and
raise when unconfigured; in pre-credential environments we fall back to a
``NoopAdapter`` for those channels so the dispatch tick keeps working while the
system is still live-ready the moment env is present.
"""

from __future__ import annotations

import logging

from app.services.notifications.adapters.base import ChannelAdapter, NoopAdapter
from app.services.notifications.adapters.email import build_email_adapter
from app.services.notifications.adapters.sms import build_sms_adapter
from app.services.notifications.adapters.whatsapp import WhatsAppAdapter

logger = logging.getLogger(__name__)


def build_adapters() -> dict[str, ChannelAdapter]:
    """Return the whatsapp/sms/email adapter map, noop-falling-back on missing env."""
    adapters: dict[str, ChannelAdapter] = {"whatsapp": WhatsAppAdapter()}

    try:
        adapters["sms"] = build_sms_adapter()
    except Exception:
        logger.warning("SMS adapter not configured, using noop", exc_info=True)
        adapters["sms"] = NoopAdapter()

    try:
        adapters["email"] = build_email_adapter()
    except Exception:
        logger.warning("Email adapter not configured, using noop", exc_info=True)
        adapters["email"] = NoopAdapter()

    return adapters
