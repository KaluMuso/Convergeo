"""Courier pickup/drop-off message — one builder for outbox + "copy message".

The same ``CourierMessage`` feeds three sinks so they can never drift:

* the WhatsApp ``courier_dispatch_request`` template (single-line body params —
  Meta rejects newlines/tabs inside template parameters),
* the Resend email fallback (``dispatch_message`` multi-line body),
* the admin board's "Copy message" fallback for pasting into WhatsApp by hand.

Money is integer ngwee end to end and rendered with ``format_k`` (the Python
twin of the shared ``formatK()``); no float ever touches the COD amount.
Coordinates are floats by nature (not money) and only ever formatted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.notifications.templates.whatsapp import format_k

MAX_ITEM_LINES = 6
_PARAM_MAX = 300


@dataclass(frozen=True, slots=True)
class Place:
    label: str
    landmark: str | None
    lat: float | None
    lng: float | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class CourierMessageContext:
    order_id: str
    courier_name: str
    pickup: Place
    dropoff: Place
    items: tuple[tuple[str, int], ...]
    cod_amount_ngwee: int
    courier_reference: str | None = None


@dataclass(frozen=True, slots=True)
class CourierMessage:
    order_reference: str
    pickup_line: str
    dropoff_line: str
    items_line: str
    cod_line: str
    contacts_line: str
    text: str

    def whatsapp_params(self) -> dict[str, str]:
        return {
            "order_reference": self.order_reference,
            "pickup_line": self.pickup_line,
            "dropoff_line": self.dropoff_line,
            "items_line": self.items_line,
            "cod_line": self.cod_line,
            "contacts_line": self.contacts_line,
        }


def order_reference(order_id: str) -> str:
    """Short human reference used on the phone with riders: ``ord-1a2b3c4d``."""
    return f"ord-{order_id.replace('-', '')[:8].lower()}"


def _one_line(value: str) -> str:
    collapsed = " ".join(value.split())
    return collapsed[:_PARAM_MAX]


def maps_link(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return f"https://maps.google.com/?q={lat:.6f},{lng:.6f}"


def _place_line(place: Place, *, unknown: str) -> str:
    parts: list[str] = []
    if place.label.strip():
        parts.append(place.label.strip())
    if place.landmark and place.landmark.strip():
        parts.append(place.landmark.strip())
    link = maps_link(place.lat, place.lng)
    if link:
        parts.append(f"GPS {link}")
    return _one_line(" - ".join(parts) if parts else unknown)


def cod_line(cod_amount_ngwee: int) -> str:
    if isinstance(cod_amount_ngwee, bool) or not isinstance(cod_amount_ngwee, int):
        raise TypeError("cod_amount_ngwee must be integer ngwee")
    if cod_amount_ngwee < 0:
        raise ValueError("cod_amount_ngwee cannot be negative")
    if cod_amount_ngwee == 0:
        return "Prepaid - collect nothing"
    return f"Collect cash on delivery: {format_k(cod_amount_ngwee)}"


def _items_line(items: tuple[tuple[str, int], ...]) -> str:
    if not items:
        return "1 parcel"
    shown = [f"{qty} x {title.strip() or 'Item'}" for title, qty in items[:MAX_ITEM_LINES]]
    extra = len(items) - MAX_ITEM_LINES
    if extra > 0:
        shown.append(f"+{extra} more")
    return _one_line("; ".join(shown))


def build_courier_message(ctx: CourierMessageContext) -> CourierMessage:
    ref = order_reference(ctx.order_id)
    pickup = _place_line(ctx.pickup, unknown="Pickup location on request")
    dropoff = _place_line(ctx.dropoff, unknown="Drop-off location on request")
    items = _items_line(ctx.items)
    cod = cod_line(ctx.cod_amount_ngwee)
    contacts = _one_line(
        f"Pickup {ctx.pickup.phone or 'n/a'}; Customer {ctx.dropoff.phone or 'n/a'}"
    )
    lines = [
        f"Vergeo5 delivery request {ref} for {ctx.courier_name}",
        f"Pickup: {pickup}",
        f"Drop-off: {dropoff}",
        f"Items: {items}",
        f"Payment: {cod}",
        f"Contacts: {contacts}",
    ]
    if ctx.courier_reference:
        lines.append(f"Your ref: {_one_line(ctx.courier_reference)}")
    lines.append(
        "The customer will give the rider a 6-digit handover code on delivery; "
        "send it to Vergeo5 ops to close the job."
    )
    return CourierMessage(
        order_reference=ref,
        pickup_line=pickup,
        dropoff_line=dropoff,
        items_line=items,
        cod_line=cod,
        contacts_line=contacts,
        text="\n".join(lines),
    )


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def context_from_row(row: dict[str, Any], *, courier_name: str) -> CourierMessageContext:
    """Build the message context from ``load_order_dispatch_context`` JSON."""
    pickup_raw = row.get("pickup") if isinstance(row.get("pickup"), dict) else {}
    dropoff_raw = row.get("dropoff") if isinstance(row.get("dropoff"), dict) else {}
    assert isinstance(pickup_raw, dict) and isinstance(dropoff_raw, dict)
    items_raw = row.get("items") if isinstance(row.get("items"), list) else []
    assert isinstance(items_raw, list)
    items: list[tuple[str, int]] = []
    for item in items_raw:
        if isinstance(item, dict):
            qty = item.get("qty")
            items.append((str(item.get("title") or "Item"), qty if isinstance(qty, int) else 1))
    cod_amount = row.get("cod_amount_ngwee")
    if isinstance(cod_amount, bool) or not isinstance(cod_amount, int):
        raise TypeError("cod_amount_ngwee must be integer ngwee")
    vendor_phone = _str_or_none(pickup_raw.get("phone")) or _str_or_none(row.get("vendor_whatsapp"))
    customer_phone = _str_or_none(dropoff_raw.get("phone")) or _str_or_none(
        row.get("customer_phone")
    )
    return CourierMessageContext(
        order_id=str(row["order_id"]),
        courier_name=courier_name,
        pickup=Place(
            label=str(row.get("vendor_name") or ""),
            landmark=_str_or_none(pickup_raw.get("landmark")),
            lat=_float_or_none(pickup_raw.get("lat")),
            lng=_float_or_none(pickup_raw.get("lng")),
            phone=vendor_phone,
        ),
        dropoff=Place(
            label=str(row.get("customer_name") or ""),
            landmark=_str_or_none(dropoff_raw.get("landmark")),
            lat=_float_or_none(dropoff_raw.get("lat")),
            lng=_float_or_none(dropoff_raw.get("lng")),
            phone=customer_phone,
        ),
        items=tuple(items),
        cod_amount_ngwee=cod_amount,
        courier_reference=_str_or_none(row.get("courier_reference")),
    )
