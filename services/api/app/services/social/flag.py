"""Feature flag ``social_contacts`` — fail closed."""

from __future__ import annotations

from typing import Any, Protocol

from app.errors import AppError

FLAG = "social_contacts"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def social_contacts_enabled(service_client: ServiceRoleClient) -> bool:
    try:
        response = (
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", FLAG)
            .maybe_single()
            .execute()
        )
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            return data.get("enabled") is True
    except Exception:
        return False
    return False


def require_social_contacts_enabled(service_client: ServiceRoleClient) -> None:
    if not social_contacts_enabled(service_client):
        raise AppError(
            code="feature_disabled",
            message="Social contacts is not available",
            http_status=404,
            details={"message_key": "social.errors.disabled"},
        )