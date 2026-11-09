"""Admin-managed courier directory (``courier_partners`` + ``courier_partner_zones``).

Writes are single SQL transactions so a partner and its service areas never
diverge (zones are replaced wholesale on update). ``integration_kind='api'`` is
reserved for the later TownStar / Yango / Platinum adapters and is refused here
until one ships — the DB accepts it so the migration need not change later.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.errors import AppError
from app.services.dispatch.state import json_rows
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import sql_uuid

E164_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ZONE_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")
RESERVED_INTEGRATION_KINDS = frozenset({"api"})


@dataclass(frozen=True, slots=True)
class ZoneInput:
    zone_key: str
    price_ngwee: int | None


@dataclass(frozen=True, slots=True)
class CourierInput:
    name: str
    contact_whatsapp_e164: str | None
    contact_email: str | None
    integration_kind: str
    active: bool
    notes: str | None
    zones: tuple[ZoneInput, ...]


def _validation(message: str, **details: Any) -> AppError:
    return AppError(code="validation_error", message=message, http_status=422, details=details)


def validate_courier_input(data: CourierInput) -> CourierInput:
    name = data.name.strip()
    if not 1 <= len(name) <= 120:
        raise _validation("name must be 1-120 characters", field="name")
    phone = (data.contact_whatsapp_e164 or "").strip() or None
    if phone is not None and not E164_RE.match(phone):
        raise _validation("contact_whatsapp_e164 must be E.164 (+260...)", field="phone")
    email = (data.contact_email or "").strip() or None
    if email is not None and (len(email) > 254 or not EMAIL_RE.match(email)):
        raise _validation("contact_email is invalid", field="contact_email")
    if phone is None and email is None:
        raise _validation("A WhatsApp number or email is required", field="contact")
    if data.integration_kind in RESERVED_INTEGRATION_KINDS:
        raise AppError(
            code="courier_integration_reserved",
            message="API courier integrations are reserved for a later release",
            http_status=422,
            details={"integration_kind": data.integration_kind},
        )
    if data.integration_kind != "manual":
        raise _validation("integration_kind must be manual", field="integration_kind")
    notes = (data.notes or "").strip() or None
    if notes is not None and len(notes) > 1000:
        raise _validation("notes must be at most 1000 characters", field="notes")
    seen: set[str] = set()
    zones: list[ZoneInput] = []
    for zone in data.zones:
        key = zone.zone_key.strip()
        if not ZONE_KEY_RE.match(key):
            raise _validation("invalid zone_key", field="zones", zone_key=key)
        if key in seen:
            raise _validation("duplicate zone_key", field="zones", zone_key=key)
        price = zone.price_ngwee
        if price is not None and (isinstance(price, bool) or price < 0):
            raise _validation("price_ngwee must be a non-negative integer", field="zones")
        seen.add(key)
        zones.append(ZoneInput(zone_key=key, price_ngwee=price))
    return CourierInput(
        name=name,
        contact_whatsapp_e164=phone,
        contact_email=email,
        integration_kind=data.integration_kind,
        active=data.active,
        notes=notes,
        zones=tuple(zones),
    )


def _nullable(value: str | None) -> str:
    return "NULL" if value is None else sql_literal(value)


def _assert_zones_exist(zones: tuple[ZoneInput, ...]) -> None:
    if not zones:
        return
    keys = ", ".join(sql_literal(zone.zone_key) for zone in zones)
    rows = json_rows(
        "SELECT json_build_object('zone_key', zone_key)::text FROM public.delivery_zones "
        f"WHERE zone_key IN ({keys});",
        context="delivery zone lookup",
    )
    known = {str(row["zone_key"]) for row in rows}
    missing = sorted(zone.zone_key for zone in zones if zone.zone_key not in known)
    if missing:
        raise _validation("unknown delivery zone", field="zones", unknown=missing)


def _zones_insert_sql(courier_ref: str, zones: tuple[ZoneInput, ...]) -> str:
    if not zones:
        return ""
    values = ", ".join(
        f"({courier_ref}, {sql_literal(zone.zone_key)}, "
        f"{'NULL' if zone.price_ngwee is None else int(zone.price_ngwee)})"
        for zone in zones
    )
    return (
        "INSERT INTO public.courier_partner_zones (courier_partner_id, zone_key, price_ngwee) "
        f"VALUES {values};"
    )


_COURIER_JSON = """json_build_object(
  'id', c.id, 'name', c.name,
  'contact_whatsapp_e164', c.contact_whatsapp_e164, 'contact_email', c.contact_email,
  'integration_kind', c.integration_kind, 'active', c.active, 'notes', c.notes,
  'created_at', c.created_at, 'updated_at', c.updated_at,
  'zones', coalesce((
    SELECT json_agg(json_build_object('zone_key', z.zone_key, 'price_ngwee', z.price_ngwee)
                    ORDER BY z.zone_key)
    FROM public.courier_partner_zones z WHERE z.courier_partner_id = c.id
  ), '[]'::json)
)"""


def list_couriers() -> list[dict[str, Any]]:
    return json_rows(
        f"SELECT {_COURIER_JSON}::text FROM public.courier_partners c "
        "ORDER BY c.active DESC, lower(c.name) ASC;",
        context="courier list",
    )


def get_courier(courier_id: str) -> dict[str, Any]:
    courier_sql = sql_uuid(courier_id, "courier_id")
    rows = json_rows(
        f"SELECT {_COURIER_JSON}::text FROM public.courier_partners c WHERE c.id = {courier_sql};",
        context="courier lookup",
    )
    if not rows:
        raise AppError(code="not_found", message="Courier not found", http_status=404)
    return rows[0]


def _duplicate_name(error: str | None) -> bool:
    return "courier_partners_name_lower_key" in (error or "")


def create_courier(data: CourierInput) -> dict[str, Any]:
    clean = validate_courier_input(data)
    _assert_zones_exist(clean.zones)
    script = f"""
BEGIN;
CREATE TEMP TABLE _new_courier ON COMMIT DROP AS
WITH ins AS (
  INSERT INTO public.courier_partners (
    name, contact_whatsapp_e164, contact_email, integration_kind, active, notes
  ) VALUES (
    {sql_literal(clean.name)}, {_nullable(clean.contact_whatsapp_e164)},
    {_nullable(clean.contact_email)}, {sql_literal(clean.integration_kind)},
    {"true" if clean.active else "false"}, {_nullable(clean.notes)}
  ) RETURNING id
) SELECT id FROM ins;
{_zones_insert_sql("(SELECT id FROM _new_courier)", clean.zones)}
SELECT json_build_object('id', id)::text FROM _new_courier;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        if _duplicate_name(result.error):
            raise AppError(
                code="courier_name_taken",
                message="A courier with this name already exists",
                http_status=409,
            )
        raise RuntimeError(f"create courier failed: {result.error}")
    created = [row for row in result.rows if row.startswith("{")]
    if not created:
        raise RuntimeError("create courier returned no row")
    return get_courier(str(json.loads(created[-1])["id"]))


def update_courier(courier_id: str, data: CourierInput) -> dict[str, Any]:
    clean = validate_courier_input(data)
    _assert_zones_exist(clean.zones)
    get_courier(courier_id)
    courier_sql = sql_uuid(courier_id, "courier_id")
    script = f"""
BEGIN;
UPDATE public.courier_partners SET
  name = {sql_literal(clean.name)},
  contact_whatsapp_e164 = {_nullable(clean.contact_whatsapp_e164)},
  contact_email = {_nullable(clean.contact_email)},
  integration_kind = {sql_literal(clean.integration_kind)},
  active = {"true" if clean.active else "false"},
  notes = {_nullable(clean.notes)}
WHERE id = {courier_sql};
DELETE FROM public.courier_partner_zones WHERE courier_partner_id = {courier_sql};
{_zones_insert_sql(courier_sql, clean.zones)}
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        if _duplicate_name(result.error):
            raise AppError(
                code="courier_name_taken",
                message="A courier with this name already exists",
                http_status=409,
            )
        raise RuntimeError(f"update courier failed: {result.error}")
    return get_courier(courier_id)
