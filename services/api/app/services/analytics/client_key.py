"""Trusted client key for the analytics rate limiter (plan §R-C).

Production chain: browser → (Vercel rewrite) → Cloudflare → Caddy → uvicorn.

* Caddy (no ``trusted_proxies``) does not let a client control the LAST hop of
  ``X-Forwarded-For``: whether it replaces or appends, the rightmost entry is the TCP
  peer Caddy actually saw. We therefore read the **rightmost** hop, never the leftmost
  (which the legacy ``core.ratelimit.get_client_ip`` uses and a client can forge).
* When that hop is a published Cloudflare edge range, Cloudflare asserted
  ``CF-Connecting-IP`` and we use it. Otherwise ``CF-Connecting-IP`` is ignored —
  anybody can send that header to a non-Cloudflare hop.

Residual risk: a caller who reaches the origin directly (bypassing Caddy) can forge
headers, but only to pick their own bucket, still bounded by the global bucket. Origin
lock to Cloudflare (OD-3) removes it. The Cloudflare list must be refreshed from
https://www.cloudflare.com/ips/ when Cloudflare publishes changes.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Final

from fastapi import Request

CLOUDFLARE_RANGES: Final[tuple[str, ...]] = (
    # IPv4 — https://www.cloudflare.com/ips-v4
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    # IPv6 — https://www.cloudflare.com/ips-v6
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)

_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in CLOUDFLARE_RANGES)


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


@lru_cache(maxsize=4096)
def is_cloudflare_ip(value: str) -> bool:
    ip = _parse_ip(value)
    return ip is not None and any(ip in network for network in _NETWORKS)


def trusted_client_key(request: Request) -> str:
    """Best trustworthy client identifier for rate limiting (an IP string or 'unknown')."""
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    last_hop = hops[-1] if hops else None
    if last_hop is None and request.client is not None:
        last_hop = request.client.host
    if last_hop and is_cloudflare_ip(last_hop):
        cf_ip = _parse_ip(request.headers.get("cf-connecting-ip"))
        if cf_ip is not None:
            return str(cf_ip)
    parsed = _parse_ip(last_hop)
    return str(parsed) if parsed is not None else "unknown"
