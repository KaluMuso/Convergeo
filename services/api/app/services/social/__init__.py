"""T28 — social contacts API helpers (phone peppering, RPC errors, flag gate)."""

from app.services.social.errors import map_social_rpc_error, raise_if_social_error_message
from app.services.social.flag import require_social_contacts_enabled, social_contacts_enabled
from app.services.social.phone import (
    client_hash_to_storage_hash,
    e164_sha256_hex,
    normalize_to_e164,
    require_phone_pepper,
)

__all__ = [
    "client_hash_to_storage_hash",
    "e164_sha256_hex",
    "map_social_rpc_error",
    "normalize_to_e164",
    "raise_if_social_error_message",
    "require_phone_pepper",
    "require_social_contacts_enabled",
    "social_contacts_enabled",
]