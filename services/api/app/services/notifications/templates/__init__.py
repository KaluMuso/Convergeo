"""Notification template registries (per-channel)."""

from app.services.notifications.templates.whatsapp import (
    WHATSAPP_TEMPLATES,
    WhatsAppTemplateId,
    build_cloud_api_template,
    format_k,
    render_whatsapp_template,
)

__all__ = [
    "WHATSAPP_TEMPLATES",
    "WhatsAppTemplateId",
    "build_cloud_api_template",
    "format_k",
    "render_whatsapp_template",
]
