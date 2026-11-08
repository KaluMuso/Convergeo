"""Vendor storefront brand theme: validation + WCAG AA clamping.

Mirrors ``packages/ui/src/brand-theme.ts``. A theme is ``{"primary", "accent"}``
as ``#RRGGBB`` (or null). Primary is darkened until white text on it reaches
4.5:1; accent until it reaches 3:1 on white. The DB check constraint
(20261108120000_vendor_brand_theme.sql) enforces the stored shape.
"""

from __future__ import annotations

import re
from typing import Any

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
PRIMARY_MIN_CONTRAST = 4.5
ACCENT_MIN_CONTRAST = 3.0
_WHITE = "#FFFFFF"


def _channel(value: float) -> float:
    s = value / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def _rgb(hex_value: str) -> tuple[float, float, float]:
    n = int(hex_value[1:], 16)
    return float((n >> 16) & 255), float((n >> 8) & 255), float(n & 255)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def relative_luminance(hex_value: str) -> float:
    r, g, b = _rgb(hex_value)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def ensure_contrast(hex_value: str, minimum: float, against: str = _WHITE) -> str:
    """Darken toward black (hue preserved) until ``minimum`` contrast is met."""
    r, g, b = _rgb(hex_value)
    current = _hex((r, g, b))
    for _ in range(40):
        if contrast_ratio(current, against) >= minimum:
            break
        r, g, b = r * 0.92, g * 0.92, b * 0.92
        current = _hex((r, g, b))
    return current


def sanitize_brand_theme(raw: Any) -> dict[str, str | None] | None:
    """Return an AA-clamped theme, or None when nothing valid remains.

    Raises ValueError for a value that is present but not ``#RRGGBB`` so the API
    can answer 422 instead of silently dropping the vendor's input.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("brand_theme must be an object")
    unknown = set(raw) - {"primary", "accent"}
    if unknown:
        raise ValueError(f"unknown brand_theme keys: {sorted(unknown)}")
    out: dict[str, str | None] = {"primary": None, "accent": None}
    for key, minimum in (("primary", PRIMARY_MIN_CONTRAST), ("accent", ACCENT_MIN_CONTRAST)):
        value = raw.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str) or not HEX_RE.match(value):
            raise ValueError(f"brand_theme.{key} must be a #RRGGBB colour")
        out[key] = ensure_contrast(value.upper(), minimum)
    if out["primary"] is None and out["accent"] is None:
        return None
    return out


def read_brand_theme(raw: Any) -> dict[str, str | None] | None:
    """Lenient read path for stored rows (never raises)."""
    try:
        return sanitize_brand_theme(raw)
    except ValueError:
        return None
