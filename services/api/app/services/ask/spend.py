from __future__ import annotations

import importlib
import logging
import threading
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from app.errors import AppError

logger = logging.getLogger(__name__)

ServiceClient = Any

DEFAULT_MONTHLY_CAP_USD = 15
DEFAULT_RATE_PER_MILLION_TOKENS = Decimal("0.15")
MICROS_PER_USD = 1_000_000

_CONFIG_CACHE_TTL_SECONDS = 60.0
_config_cache: dict[str, tuple[float, Any]] = {}
_config_lock = threading.Lock()


def _service_client() -> Any:
    return importlib.import_module("app.supabase_client").get_supabase_service_client().client


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _rpc_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [cast(dict[str, Any], data)]
    return []


def current_month_key(now: datetime | None = None) -> str:
    instant = now or datetime.now(UTC)
    return instant.strftime("%Y-%m")


def clear_spend_config_cache() -> None:
    with _config_lock:
        _config_cache.clear()


def _read_platform_config_value(client: ServiceClient, key: str) -> Any | None:
    now = datetime.now(UTC).timestamp()
    with _config_lock:
        cached = _config_cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

    try:
        response = (
            client.table("platform_config").select("value").eq("key", key).maybe_single().execute()
        )
        value = _single_row(response)
        parsed = value.get("value") if value else None
    except Exception:
        logger.warning("Failed to read platform_config key %s", key, exc_info=True)
        parsed = None

    with _config_lock:
        _config_cache[key] = (now + _CONFIG_CACHE_TTL_SECONDS, parsed)
    return parsed


def monthly_cap_usd_micros(client: ServiceClient | None = None) -> int:
    service = client or _service_client()
    raw = _read_platform_config_value(service, "ai_monthly_cap_usd")
    cap_usd = DEFAULT_MONTHLY_CAP_USD
    if isinstance(raw, int):
        cap_usd = raw
    elif isinstance(raw, float):
        cap_usd = int(raw)
    elif isinstance(raw, str) and raw.isdigit():
        cap_usd = int(raw)
    return cap_usd * MICROS_PER_USD


def _parse_model_rates(raw: Any) -> dict[str, Decimal]:
    if not isinstance(raw, dict):
        return {"default": DEFAULT_RATE_PER_MILLION_TOKENS}

    rates: dict[str, Decimal] = {}
    for key, value in raw.items():
        try:
            rates[str(key)] = Decimal(str(value))
        except Exception:
            logger.warning("Skipping invalid ai_model_rates entry for %s", key)
    if "default" not in rates:
        rates["default"] = DEFAULT_RATE_PER_MILLION_TOKENS
    return rates


def model_rates(client: ServiceClient | None = None) -> dict[str, Decimal]:
    service = client or _service_client()
    raw = _read_platform_config_value(service, "ai_model_rates")
    return _parse_model_rates(raw)


def tokens_to_usd_micros(*, tokens: int, model: str, client: ServiceClient | None = None) -> int:
    if tokens <= 0:
        return 0

    rates = model_rates(client)
    rate = rates.get(model) or rates.get("default", DEFAULT_RATE_PER_MILLION_TOKENS)
    usd = (Decimal(tokens) * rate) / Decimal(1_000_000)
    micros = (usd * Decimal(MICROS_PER_USD)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(micros)


def _monthly_spend_row(client: ServiceClient, month_key: str) -> dict[str, Any] | None:
    response = (
        client.table("ask_spend_monthly")
        .select("month_key,total_usd_micros,killed_at,admin_reset_at")
        .eq("month_key", month_key)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def is_killed(*, client: ServiceClient | None = None, month_key: str | None = None) -> bool:
    service = client or _service_client()
    key = month_key or current_month_key()
    row = _monthly_spend_row(service, key)
    if row is None:
        return False

    killed_at = row.get("killed_at")
    if not killed_at:
        return False

    admin_reset_at = row.get("admin_reset_at")
    if admin_reset_at and str(admin_reset_at) >= str(killed_at):
        return False
    return True


def reset_kill_switch(
    *,
    client: ServiceClient | None = None,
    month_key: str | None = None,
) -> bool:
    service = client or _service_client()
    params: dict[str, Any] = {}
    if month_key is not None:
        params["p_month_key"] = month_key
    response = service.rpc("reset_ask_kill_switch", params).execute()
    data = getattr(response, "data", None)
    return bool(data)


def raise_if_killed(*, client: ServiceClient | None = None) -> None:
    if is_killed(client=client):
        raise AppError(
            code="ai_quota_kill_switch",
            message="ai.quota.killSwitch",
            http_status=503,
            details={"i18n_key": "ai.quota.killSwitch"},
        )


def record_spend(
    *,
    reservation_id: str,
    tokens: int,
    model: str,
    client: ServiceClient | None = None,
) -> dict[str, Any]:
    service = client or _service_client()
    usd_micros = tokens_to_usd_micros(tokens=tokens, model=model, client=service)
    response = service.rpc(
        "finalize_ask_answer",
        {
            "p_reservation_id": reservation_id,
            "p_tokens": tokens,
            "p_model": model,
            "p_usd_micros": usd_micros,
        },
    ).execute()
    rows = _rpc_rows(response)
    if not rows:
        raise RuntimeError("finalize_ask_answer returned no rows")
    return rows[0]
