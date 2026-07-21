"""WhatsApp Cloud API template registry — variable mapping and payload builder."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.schemas.base import parse_ngwee

WhatsAppTemplateId = Literal[
    "order_confirmed",
    "payment_received",
    "order_shipped",
    "order_ready_pickup",
    "order_delivered",
    "vendor_new_order",
    "otp_login",
    "rfq_job_broadcast",
    "compliance_confirmation",
    "event_cancelled",
    "event_schedule_changed",
]

SUPPORTED_LOCALES = frozenset({"en", "bem", "nya"})

# Meta Graph API language codes per Vergeo5 locale slot.
META_LANGUAGE_CODES: dict[str, str] = {
    "en": "en",
    "bem": "bem_ZM",
    "nya": "nya_ZM",
}

# Env var names for per-number token configuration (no literals in code).
WHATSAPP_TOKEN_ENV = "WHATSAPP_TOKEN"
WHATSAPP_ACCESS_TOKEN_ENV = "WHATSAPP_ACCESS_TOKEN"
WHATSAPP_PHONE_NUMBER_ID_ENV = "WHATSAPP_PHONE_NUMBER_ID"
WHATSAPP_API_VERSION_ENV = "WHATSAPP_API_VERSION"
DEFAULT_API_VERSION = "v23.0"


class TemplateRenderError(ValueError):
    """Raised when outbox payload cannot be mapped to a WhatsApp template."""


class CloudApiTemplatePayload(TypedDict):
    messaging_product: str
    to: str
    type: str
    template: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RenderedWhatsAppTemplate:
    template_id: WhatsAppTemplateId
    meta_template_name: str
    language_code: str
    to_e164: str
    body_parameters: tuple[str, ...]
    button_parameters: tuple[str, ...] = ()
    phone_number_id_env: str = WHATSAPP_PHONE_NUMBER_ID_ENV
    token_env: str = WHATSAPP_TOKEN_ENV


def format_k(ngwee: int) -> str:
    """formatK-equivalent: integer ngwee → ``K1,234.56`` (en-ZM grouping, no float)."""
    validated = parse_ngwee(ngwee)
    negative = validated < 0
    absolute = abs(validated)
    major_units = absolute // 100
    minor_units = absolute % 100
    formatted = f"{major_units:,}.{minor_units:02d}"
    return f"-K{formatted}" if negative else f"K{formatted}"


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"payload[{key!r}] must be a non-empty string"
        raise TemplateRenderError(msg)
    return value.strip()


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if value is None:
        msg = f"payload[{key!r}] is required"
        raise TemplateRenderError(msg)
    return parse_ngwee(value)


def _locale(payload: Mapping[str, Any]) -> str:
    raw = payload.get("locale", "en")
    if not isinstance(raw, str):
        msg = "payload['locale'] must be a string"
        raise TemplateRenderError(msg)
    locale = raw.strip().lower()
    if locale not in SUPPORTED_LOCALES:
        msg = f"unsupported locale: {locale!r}"
        raise TemplateRenderError(msg)
    return locale


def _localized_slot(payload: Mapping[str, Any], key: str, *, fallback: str) -> str:
    """Return a pre-localized i18n slot from payload, or the EN fallback."""
    slots = payload.get("i18n_slots")
    if isinstance(slots, Mapping):
        value = slots.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _map_order_confirmed(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _require_str(payload, "order_reference"),
        format_k(_require_int(payload, "total_ngwee")),
        _require_str(payload, "track_url"),
    )


def _map_payment_received(payload: Mapping[str, Any]) -> tuple[str, ...]:
    amount = format_k(_require_int(payload, "amount_ngwee"))
    order_ref = _require_str(payload, "order_reference")
    locale = _locale(payload)
    trust_line = _localized_slot(
        payload,
        "trust_narrative",
        fallback=(
            f"Your {amount} is held safely by Vergeo5 until delivery."
            if locale == "en"
            else f"Your {amount} is held safely by Vergeo5 until delivery."
        ),
    )
    return (trust_line, order_ref)


def _map_order_shipped(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _require_str(payload, "order_reference"),
        _require_str(payload, "tracking_info"),
    )


def _map_order_ready_pickup(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _require_str(payload, "order_reference"),
        _require_str(payload, "pickup_details"),
    )


def _map_order_delivered(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _require_str(payload, "order_reference"),
        _require_str(payload, "review_url"),
    )


def _map_vendor_new_order(payload: Mapping[str, Any]) -> tuple[str, ...]:
    qty = payload.get("quantity")
    if not isinstance(qty, int) or qty < 1:
        msg = "payload['quantity'] must be a positive integer"
        raise TemplateRenderError(msg)
    return (
        _require_str(payload, "order_reference"),
        _require_str(payload, "product_title"),
        str(qty),
    )


def _map_otp_login(payload: Mapping[str, Any]) -> tuple[str, ...]:
    code = _require_str(payload, "otp_code")
    if not code.isdigit() or len(code) < 4:
        msg = "payload['otp_code'] must be a numeric OTP string"
        raise TemplateRenderError(msg)
    return (code,)


def _map_rfq_job_broadcast(payload: Mapping[str, Any]) -> tuple[str, ...]:
    # Provider RFQ broadcast: category (required), plus service area and a short
    # description preview. The latter two fall back to non-empty text because Meta
    # rejects template sends with empty body parameters.
    category = _require_str(payload, "category")
    area = payload.get("service_area")
    area_str = area.strip() if isinstance(area, str) and area.strip() else "Zambia"
    preview = payload.get("description_preview")
    preview_str = (
        preview.strip() if isinstance(preview, str) and preview.strip() else "New job request"
    )
    return (category, area_str, preview_str)


def _map_compliance_confirmation(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return (_require_str(payload, "confirmation_body"),)


def _map_event_cancelled(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _require_str(payload, "event_title"),
        _require_str(payload, "event_date"),
        _require_str(payload, "refund_detail"),
    )


def _map_event_schedule_changed(payload: Mapping[str, Any]) -> tuple[str, ...]:
    venue = payload.get("venue")
    venue_str = venue.strip() if isinstance(venue, str) and venue.strip() else "See the app"
    return (
        _require_str(payload, "event_title"),
        _require_str(payload, "event_date"),
        venue_str,
    )


@dataclass(frozen=True, slots=True)
class WhatsAppTemplateDefinition:
    template_id: WhatsAppTemplateId
    meta_template_name: str
    map_variables: Callable[[Mapping[str, Any]], tuple[str, ...]]
    has_copy_code_button: bool = False


WHATSAPP_TEMPLATES: dict[WhatsAppTemplateId, WhatsAppTemplateDefinition] = {
    "order_confirmed": WhatsAppTemplateDefinition(
        template_id="order_confirmed",
        meta_template_name="order_confirmed",
        map_variables=_map_order_confirmed,
    ),
    "payment_received": WhatsAppTemplateDefinition(
        template_id="payment_received",
        meta_template_name="payment_received",
        map_variables=_map_payment_received,
    ),
    "order_shipped": WhatsAppTemplateDefinition(
        template_id="order_shipped",
        meta_template_name="order_shipped",
        map_variables=_map_order_shipped,
    ),
    "order_ready_pickup": WhatsAppTemplateDefinition(
        template_id="order_ready_pickup",
        meta_template_name="order_ready_pickup",
        map_variables=_map_order_ready_pickup,
    ),
    "order_delivered": WhatsAppTemplateDefinition(
        template_id="order_delivered",
        meta_template_name="order_delivered",
        map_variables=_map_order_delivered,
    ),
    "vendor_new_order": WhatsAppTemplateDefinition(
        template_id="vendor_new_order",
        meta_template_name="vendor_new_order",
        map_variables=_map_vendor_new_order,
    ),
    "otp_login": WhatsAppTemplateDefinition(
        template_id="otp_login",
        meta_template_name="otp_login",
        map_variables=_map_otp_login,
        has_copy_code_button=True,
    ),
    "rfq_job_broadcast": WhatsAppTemplateDefinition(
        template_id="rfq_job_broadcast",
        meta_template_name="rfq_job_broadcast",
        map_variables=_map_rfq_job_broadcast,
    ),
    "compliance_confirmation": WhatsAppTemplateDefinition(
        template_id="compliance_confirmation",
        meta_template_name="compliance_confirmation",
        map_variables=_map_compliance_confirmation,
    ),
    "event_cancelled": WhatsAppTemplateDefinition(
        template_id="event_cancelled",
        meta_template_name="event_cancelled",
        map_variables=_map_event_cancelled,
    ),
    "event_schedule_changed": WhatsAppTemplateDefinition(
        template_id="event_schedule_changed",
        meta_template_name="event_schedule_changed",
        map_variables=_map_event_schedule_changed,
    ),
}


def render_whatsapp_template(
    template_id: str,
    payload: Mapping[str, Any],
) -> RenderedWhatsAppTemplate:
    """Map an outbox template id + payload to rendered Cloud API parameters."""
    if template_id not in WHATSAPP_TEMPLATES:
        msg = f"unknown WhatsApp template: {template_id!r}"
        raise TemplateRenderError(msg)

    definition = WHATSAPP_TEMPLATES[template_id]
    locale = _locale(payload)
    to_e164 = _require_str(payload, "to")
    body_parameters = definition.map_variables(payload)
    button_parameters: tuple[str, ...] = ()
    if definition.has_copy_code_button and body_parameters:
        button_parameters = (body_parameters[0],)

    token_env = WHATSAPP_TOKEN_ENV
    if isinstance(payload.get("token_env"), str) and payload["token_env"].strip():
        token_env = payload["token_env"].strip()

    phone_env = WHATSAPP_PHONE_NUMBER_ID_ENV
    phone_number_id_env = payload.get("phone_number_id_env")
    if isinstance(phone_number_id_env, str) and phone_number_id_env.strip():
        phone_env = phone_number_id_env.strip()

    return RenderedWhatsAppTemplate(
        template_id=definition.template_id,
        meta_template_name=definition.meta_template_name,
        language_code=META_LANGUAGE_CODES[locale],
        to_e164=to_e164,
        body_parameters=body_parameters,
        button_parameters=button_parameters,
        phone_number_id_env=phone_env,
        token_env=token_env,
    )


def build_cloud_api_template(rendered: RenderedWhatsAppTemplate) -> CloudApiTemplatePayload:
    """Build the WhatsApp Cloud API ``messages`` POST body for a template send."""
    components: list[dict[str, Any]] = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": value} for value in rendered.body_parameters],
        }
    ]
    if rendered.button_parameters:
        components.append(
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [
                    {"type": "text", "text": value} for value in rendered.button_parameters
                ],
            }
        )

    return {
        "messaging_product": "whatsapp",
        "to": rendered.to_e164,
        "type": "template",
        "template": {
            "name": rendered.meta_template_name,
            "language": {"code": rendered.language_code},
            "components": components,
        },
    }
