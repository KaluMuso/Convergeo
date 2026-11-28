"""Service archetypes: how a service is offered and booked (docs/plan/service-type-templates.md).

A vertical is a browse category; an archetype picks the page template, the offer
attribute shape and the booking-request fields. ``services.archetype`` is a nullable
override: null means "derived from the vertical". (Unrelated to ``vendors.archetype``,
the seller business type.)

Offer attributes live in ``service_packages.attributes`` and service-level attributes in
``services.attributes``. Writes are validated strictly (unknown keys refused, bounded
sizes, money in integer ngwee). Reads use the tolerant variants, which return ``{}`` for
a stored blob that no longer validates, so a bad row degrades to the generic layout
instead of breaking the page (ST-7).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Final, Literal, get_args

from pydantic import ConfigDict, Field, StringConstraints, ValidationError, field_validator

from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel

Archetype = Literal[
    "accommodation",
    "appointment",
    "membership",
    "on_site",
    "rental",
    "ticketed",
    "professional",
]
ARCHETYPES: Final[tuple[str, ...]] = get_args(Archetype)
DEFAULT_ARCHETYPE: Final = "professional"

VERTICAL_ARCHETYPE: Final[dict[str, str]] = {
    "lodging": "accommodation",
    "property": "accommodation",
    "beauty": "appointment",
    "tailoring": "appointment",
    "auto": "appointment",
    "fitness": "membership",
    "cleaning": "on_site",
    "home-services": "on_site",
    "rentals": "rental",
    "family-fun": "ticketed",
    "tech-services": "professional",
    "printing-creative": "professional",
    "food-catering": "professional",
    "staffing": "professional",
    "logistics": "professional",
    "packaging": "professional",
}

MAX_ATTRIBUTES_BYTES: Final = 8000
IMAGE_RE: Final = re.compile(r"^[A-Za-z0-9_\-./]{1,200}$")
TIME_RE: Final = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
HHMM = Annotated[str, StringConstraints(pattern=TIME_RE.pattern)]


def derive_archetype(category: str | None) -> str:
    return VERTICAL_ARCHETYPE.get(str(category or ""), DEFAULT_ARCHETYPE)


def effective_archetype(row: dict[str, Any]) -> str:
    """The stored override when valid, else derived from the vertical."""
    stored = row.get("archetype")
    if isinstance(stored, str) and stored in ARCHETYPES:
        return stored
    return derive_archetype(row.get("category"))


class _Attrs(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# --------------------------------------------------------------------------- offers
class _OfferBase(_Attrs):
    #: Cloudinary public id of the offer photo.
    image: str | None = None

    @field_validator("image")
    @classmethod
    def _image(cls, value: str | None) -> str | None:
        if value is not None and not IMAGE_RE.match(value):
            msg = "image must be a Cloudinary public id"
            raise ValueError(msg)
        return value


class AccommodationOffer(_OfferBase):
    room_type: Literal["standard", "premium", "presidential", "family", "dorm", "other"] = (
        "standard"
    )
    stay_kind: Literal["nightly", "monthly"] = "nightly"
    sleeps: int = Field(default=2, ge=1, le=20)
    beds: int = Field(default=1, ge=1, le=10)
    bed_type: Literal["single", "double", "queen", "king", "bunk"] | None = None
    size_sqm: int | None = Field(default=None, ge=5, le=2000)
    amenities: list[Tag] = Field(default_factory=list, max_length=10)
    breakfast_included: bool = False
    min_nights: int = Field(default=1, ge=1, le=30)
    units_available: int | None = Field(default=None, ge=0, le=500)


class AppointmentOffer(_OfferBase):
    duration_min: int = Field(default=30, ge=5, le=480)
    group: Tag | None = None
    staff: list[Tag] = Field(default_factory=list, max_length=6)
    home_visit: bool = False
    price_is_from: bool = False

    @field_validator("duration_min")
    @classmethod
    def _step(cls, value: int) -> int:
        if value % 5:
            msg = "duration_min must be a multiple of 5"
            raise ValueError(msg)
        return value


class MembershipOffer(_OfferBase):
    pass_kind: Literal["day", "week", "month", "quarter", "year", "class_pack"] = "month"
    valid_days: int = Field(default=30, ge=1, le=730)
    visits_included: int | None = Field(default=None, ge=1, le=1000)
    classes_included: bool = False
    guest_passes: int = Field(default=0, ge=0, le=10)
    peak_hours_only: bool = False


class OnSiteOffer(_OfferBase):
    pricing_unit: Literal["hour", "visit", "room"] = "visit"
    min_hours: int = Field(default=1, ge=1, le=12)
    home_size: Literal["studio", "one_two_bed", "three_bed", "four_plus"] | None = None
    crew_size: int = Field(default=1, ge=1, le=10)
    supplies_included: bool = False


class Spec(_Attrs):
    label: Tag
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class RentalOffer(_OfferBase):
    unit: Literal["hour", "day", "week"] = "day"
    #: Informational only: collected by the vendor, never by Vergeo5 (ST-8).
    deposit_ngwee: NgweeInt | None = None
    quantity_available: int | None = Field(default=None, ge=0, le=500)
    specs: list[Spec] = Field(default_factory=list, max_length=8)
    with_operator: bool = False
    delivery_available: bool = False
    min_period: int = Field(default=1, ge=1, le=30)

    @field_validator("deposit_ngwee")
    @classmethod
    def _deposit(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            msg = "deposit_ngwee must be greater than zero when provided"
            raise ValueError(msg)
        return value


class TicketedOffer(_OfferBase):
    ticket_kind: Literal["adult", "child", "toddler", "senior", "family", "group"] = "adult"
    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    party_size: int = Field(default=1, ge=1, le=20)
    entry: Literal["any_time", "timed"] = "any_time"
    slot_capacity: int | None = Field(default=None, ge=1, le=5000)

    @field_validator("age_max")
    @classmethod
    def _ages(cls, value: int | None, info: Any) -> int | None:
        low = info.data.get("age_min")
        if value is not None and low is not None and value < low:
            msg = "age_max must be at least age_min"
            raise ValueError(msg)
        return value


class ProfessionalOffer(_OfferBase):
    rate_unit: Literal["hour", "day", "month", "project"] | None = None
    role: Tag | None = None
    experience_years: int | None = Field(default=None, ge=0, le=50)
    availability: Literal["now", "week", "booked"] | None = None
    certifications: list[Tag] = Field(default_factory=list, max_length=5)


OFFER_MODELS: Final[dict[str, type[_OfferBase]]] = {
    "accommodation": AccommodationOffer,
    "appointment": AppointmentOffer,
    "membership": MembershipOffer,
    "on_site": OnSiteOffer,
    "rental": RentalOffer,
    "ticketed": TicketedOffer,
    "professional": ProfessionalOffer,
}


# ------------------------------------------------------------------------- services
class DayHours(_Attrs):
    day: int = Field(ge=0, le=6)
    open: HHMM
    close: HHMM


class Policy(_Attrs):
    cancellation: Literal["flexible", "moderate", "strict"] | None = None
    note: Note | None = None


class StaffMember(_Attrs):
    name: Tag
    role: Tag | None = None


class ClassSlot(_Attrs):
    day: int = Field(ge=0, le=6)
    start: HHMM
    title: Tag
    duration_min: int = Field(default=60, ge=5, le=480)
    capacity: int | None = Field(default=None, ge=1, le=500)


class _ServiceBase(_Attrs):
    amenities: list[Tag] = Field(default_factory=list, max_length=12)
    #: Vendor-declared hint, not a live calendar (ST-5).
    availability: Literal["available", "limited", "unavailable"] = "available"
    hours: list[DayHours] = Field(default_factory=list, max_length=7)
    policy: Policy | None = None


class AccommodationService(_ServiceBase):
    check_in: HHMM | None = None
    check_out: HHMM | None = None


class AppointmentService(_ServiceBase):
    staff: list[StaffMember] = Field(default_factory=list, max_length=10)
    walk_ins: bool = False


class MembershipService(_ServiceBase):
    class_schedule: list[ClassSlot] = Field(default_factory=list, max_length=21)


class OnSiteService(_ServiceBase):
    pass


class RentalService(_ServiceBase):
    pickup_note: Note | None = None


class TicketedService(_ServiceBase):
    age_policy: Note | None = None


class ProfessionalService(_ServiceBase):
    pass


SERVICE_MODELS: Final[dict[str, type[_ServiceBase]]] = {
    "accommodation": AccommodationService,
    "appointment": AppointmentService,
    "membership": MembershipService,
    "on_site": OnSiteService,
    "rental": RentalService,
    "ticketed": TicketedService,
    "professional": ProfessionalService,
}


# --------------------------------------------------------------------------- helpers
def _validate(
    models: dict[str, type[Any]], archetype: str, raw: Any, *, field: str
) -> dict[str, Any]:
    model = models.get(archetype, models[DEFAULT_ARCHETYPE])
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise _invalid(field, "attributes must be an object")
    try:
        parsed = model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first.get("loc", ()))
        raise _invalid(field, f"{where}: {first.get('msg', 'invalid')}") from exc
    # Only what the vendor supplied (defaults are applied by the readers).
    return {k: v for k, v in parsed.model_dump(mode="json", exclude_unset=True).items()}


def _invalid(field: str, detail: str) -> AppError:
    return AppError(
        code="invalid_attributes",
        message=f"Invalid {field}: {detail}",
        http_status=422,
        details={"field": field, "message_key": "services.vendor.attributes.errors.invalid"},
    )


def _size_ok(value: dict[str, Any]) -> bool:
    import json

    return len(json.dumps(value, separators=(",", ":"))) <= MAX_ATTRIBUTES_BYTES


def validate_offer_attributes(archetype: str, raw: Any) -> dict[str, Any]:
    cleaned = _validate(OFFER_MODELS, archetype, raw, field="attributes")
    if not _size_ok(cleaned):
        raise _invalid("attributes", "too large")
    return cleaned


def validate_service_attributes(archetype: str, raw: Any) -> dict[str, Any]:
    cleaned = _validate(SERVICE_MODELS, archetype, raw, field="attributes")
    if not _size_ok(cleaned):
        raise _invalid("attributes", "too large")
    return cleaned


def tolerant_offer_attributes(archetype: str, raw: Any) -> dict[str, Any]:
    """Read path: ``{}`` when the stored blob no longer validates (ST-7)."""
    try:
        return validate_offer_attributes(archetype, raw)
    except AppError:
        return {}


def tolerant_service_attributes(archetype: str, raw: Any) -> dict[str, Any]:
    try:
        return validate_service_attributes(archetype, raw)
    except AppError:
        return {}


def attribute_text(value: Any) -> str:
    """All strings in an attributes blob, for the prohibited-content screen (SP-9)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(attribute_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(attribute_text(v) for v in value)
    return ""
