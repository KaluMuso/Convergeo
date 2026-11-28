"""Pydantic v2 strict models for service packages (docs/plan/service-packages.md).

A service carries an open, vendor-ordered list of packages (cap 10, see
``state.MAX_ACTIVE_PACKAGES``). ``tier`` is only a legacy label on rows that
predate the open list.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.base import NgweeInt, StrictModel
from app.services.service_packages.state import MAX_ACTIVE_PACKAGES, int_or_none

Tier = Literal["basic", "standard", "premium"]
PackageStatus = Literal["active", "archived"]

NAME_MIN = 2
NAME_MAX = 40
DESCRIPTION_MAX = 300
DELIVERY_DAYS_MIN = 1
DELIVERY_DAYS_MAX = 90
REVISIONS_MAX = 10
INCLUDES_MAX = 8
INCLUDE_ITEM_MAX = 120


class PackageUpsertRequest(StrictModel):
    """Create or update one package. ``price_ngwee=None`` means "request a quote"."""

    name: str = Field(min_length=NAME_MIN, max_length=NAME_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    price_ngwee: NgweeInt | None = None
    delivery_days: int = Field(ge=DELIVERY_DAYS_MIN, le=DELIVERY_DAYS_MAX)
    revisions: int | None = Field(default=None, ge=0, le=REVISIONS_MAX)
    includes: list[str] = Field(default_factory=list, max_length=INCLUDES_MAX)
    #: Archetype-specific offer attributes; validated by the router against the
    #: service's effective archetype (docs/plan/service-type-templates.md).
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def _strip_description(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("price_ngwee")
    @classmethod
    def _positive_price(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            msg = "price_ngwee must be greater than zero, or null for request-a-quote"
            raise ValueError(msg)
        return value

    @field_validator("includes")
    @classmethod
    def _clean_includes(cls, items: list[str]) -> list[str]:
        cleaned = [item.strip() for item in items]
        if any(not item for item in cleaned):
            msg = "include items must not be empty"
            raise ValueError(msg)
        if any(len(item) > INCLUDE_ITEM_MAX for item in cleaned):
            msg = f"include items must be at most {INCLUDE_ITEM_MAX} characters"
            raise ValueError(msg)
        return cleaned


class PackageReorderRequest(StrictModel):
    """The full desired order of the service's ACTIVE packages (ids, first = top)."""

    ids: list[str] = Field(min_length=1, max_length=MAX_ACTIVE_PACKAGES)

    @field_validator("ids")
    @classmethod
    def _unique_ids(cls, ids: list[str]) -> list[str]:
        if len(set(ids)) != len(ids):
            msg = "package ids must be unique"
            raise ValueError(msg)
        return ids


class PublicPackageOut(StrictModel):
    id: str
    tier: Tier | None = None
    sort_order: int = 0
    name: str
    description: str | None = None
    price_ngwee: int | None = None
    delivery_days: int
    revisions: int | None = None
    includes: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class VendorPackageOut(PublicPackageOut):
    status: PackageStatus
    updated_at: str | None = None


class VendorPackageListResponse(StrictModel):
    service_id: str
    max_packages: int = MAX_ACTIVE_PACKAGES
    items: list[VendorPackageOut]


def _includes(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def to_public(row: dict[str, Any]) -> PublicPackageOut:
    return PublicPackageOut(
        id=str(row["id"]),
        tier=row.get("tier") or None,
        sort_order=int_or_none(row.get("sort_order")) or 0,
        name=str(row.get("name") or ""),
        description=row.get("description") or None,
        price_ngwee=int_or_none(row.get("price_ngwee")),
        delivery_days=int_or_none(row.get("delivery_days")) or DELIVERY_DAYS_MIN,
        revisions=int_or_none(row.get("revisions")),
        includes=_includes(row.get("includes")),
        attributes=dict(row["attributes"]) if isinstance(row.get("attributes"), dict) else {},
    )


def to_vendor(row: dict[str, Any]) -> VendorPackageOut:
    public = to_public(row)
    return VendorPackageOut(
        **public.model_dump(),
        status=row.get("status") or "active",
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )
