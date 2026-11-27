"""Event archetypes: presentation templates and their validated optional content.

An archetype is *presentation only* (page layout blocks and organiser form fields).
It must never influence payments, holds, QR issuance, fees, escrow or refunds; those
read ``event_type`` (see ``type_policy.py``), never this module (spec rule A-1:
``docs/plan/event-type-templates.md``).

``events.archetype`` is NULL while derived from the category; a stored value is an
organiser override. ``events.archetype_details`` holds the per-archetype content, which
is validated here on every write and re-validated (degrading to ``{}``) on every read.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from app.errors import AppError
from app.schemas.base import StrictModel
from pydantic import AfterValidator, Field, ValidationError

EventArchetype = Literal[
    "concert",
    "religious",
    "sports_family",
    "restaurant",
    "private_gathering",
    "branded",
    "generic",
]

ARCHETYPES: tuple[EventArchetype, ...] = (
    "concert",
    "religious",
    "sports_family",
    "restaurant",
    "private_gathering",
    "branded",
    "generic",
)

MAX_DETAILS_BYTES = 16_000

CATEGORY_ARCHETYPE: dict[str, EventArchetype] = {
    "music": "concert",
    "concerts": "concert",
    "festivals": "concert",
    "gospel": "concert",
    "nightlife": "concert",
    "comedy-theatre-parent": "concert",
    "comedy-theatre": "concert",
    "stand-up": "concert",
    "religious": "religious",
    "church": "religious",
    "sports": "sports_family",
    "football": "sports_family",
    "family": "sports_family",
    "pop-up-dinners": "restaurant",
    "private-events": "private_gathering",
}


def derive_archetype(category_slug: str | None, event_type: str | None = None) -> EventArchetype:
    """Archetype implied by the category (and ``event_type = private``)."""
    if category_slug and category_slug in CATEGORY_ARCHETYPE:
        return CATEGORY_ARCHETYPE[category_slug]
    if event_type == "private":
        return "private_gathering"
    return "generic"


def normalize_archetype(value: object) -> EventArchetype | None:
    for candidate in ARCHETYPES:
        if value == candidate:
            return candidate
    return None


def resolve_archetype(
    stored: object, category_slug: str | None, event_type: str | None = None
) -> tuple[EventArchetype, Literal["derived", "override"]]:
    override = normalize_archetype(stored)
    if override is not None:
        return override, "override"
    return derive_archetype(category_slug, event_type), "derived"


# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_\-.]{0,199}$")


def _check_time(value: str) -> str:
    if not _TIME_RE.match(value):
        msg = "time must be HH:MM (24h)"
        raise ValueError(msg)
    return value


def _check_https(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        msg = "url must be https"
        raise ValueError(msg)
    return value


def _check_image(value: str) -> str:
    """Cloudinary public id or an https URL (never javascript:/data:)."""
    if value.startswith(("http://", "https://")):
        return _check_https(value)
    if not _PUBLIC_ID_RE.match(value) or ".." in value:
        msg = "image must be a Cloudinary public id or https URL"
        raise ValueError(msg)
    return value


TimeOfDay = Annotated[str, AfterValidator(_check_time)]
HttpsUrl = Annotated[str, Field(max_length=300), AfterValidator(_check_https)]
ImageRef = Annotated[str, Field(max_length=300), AfterValidator(_check_image)]
Short = Annotated[str, Field(min_length=1, max_length=80)]
Medium = Annotated[str, Field(min_length=1, max_length=200)]
Long = Annotated[str, Field(min_length=1, max_length=500)]

AgePolicy = Literal["all_ages", "guardian_under_12", "16_plus", "18_plus"]


class Sponsor(StrictModel):
    name: Short
    logo: ImageRef | None = None
    link_url: HttpsUrl | None = None
    tagline: Annotated[str, Field(max_length=120)] | None = None


class Faq(StrictModel):
    question: Annotated[str, Field(min_length=1, max_length=120)]
    answer: Long


class AgendaItem(StrictModel):
    time: TimeOfDay
    title: Medium
    speaker: Short | None = None
    notes: Annotated[str, Field(max_length=300)] | None = None


class Person(StrictModel):
    name: Short
    role: Annotated[str, Field(max_length=60)] | None = None
    image: ImageRef | None = None
    bio: Annotated[str, Field(max_length=200)] | None = None


class LineupAct(StrictModel):
    name: Short
    role: Literal["headliner", "support", "dj", "mc", "guest"] = "support"
    stage: Annotated[str, Field(max_length=60)] | None = None
    slot: TimeOfDay | None = None
    image: ImageRef | None = None
    bio: Annotated[str, Field(max_length=200)] | None = None


class Activity(StrictModel):
    name: Short
    age_group: Annotated[str, Field(max_length=40)] | None = None
    time: TimeOfDay | None = None
    area: Annotated[str, Field(max_length=60)] | None = None


class AgeGroup(StrictModel):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    min_age: int = Field(ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)


class MenuItem(StrictModel):
    name: Short
    description: Annotated[str, Field(max_length=160)] | None = None
    # Integer ngwee (convention #1). Display only: tickets carry the real price.
    price_ngwee: int | None = Field(default=None, ge=0, le=100_000_000)
    dietary: list[Literal["vegetarian", "vegan", "halal", "gluten_free", "spicy"]] = Field(
        default_factory=list, max_length=5
    )


class MenuSection(StrictModel):
    title: Short
    items: list[MenuItem] = Field(min_length=1, max_length=12)


class Activation(StrictModel):
    title: Short
    description: Annotated[str, Field(max_length=200)] | None = None


# ---------------------------------------------------------------------------
# Per-archetype models (extra keys forbidden by StrictModel)
# ---------------------------------------------------------------------------


class CommonDetails(StrictModel):
    sponsors: list[Sponsor] = Field(default_factory=list, max_length=6)
    dress_code: Annotated[str, Field(max_length=80)] | None = None
    age_policy: AgePolicy | None = None
    faqs: list[Faq] = Field(default_factory=list, max_length=8)


class ConcertDetails(CommonDetails):
    lineup: list[LineupAct] = Field(default_factory=list, max_length=30)
    stages: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=6
    )
    doors_open: TimeOfDay | None = None
    merch_note: Annotated[str, Field(max_length=200)] | None = None


class ReligiousDetails(CommonDetails):
    agenda: list[AgendaItem] = Field(default_factory=list, max_length=30)
    speakers: list[Person] = Field(default_factory=list, max_length=12)
    denomination: Annotated[str, Field(max_length=60)] | None = None
    donation_note: Annotated[str, Field(max_length=300)] | None = None
    livestream_url: HttpsUrl | None = None
    languages: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(
        default_factory=list, max_length=4
    )


class SportsFamilyDetails(CommonDetails):
    activities: list[Activity] = Field(default_factory=list, max_length=20)
    age_groups: list[AgeGroup] = Field(default_factory=list, max_length=8)
    bring_list: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=10
    )
    family_bundle_note: Annotated[str, Field(max_length=300)] | None = None


class RestaurantDetails(CommonDetails):
    menu_sections: list[MenuSection] = Field(default_factory=list, max_length=6)
    seating_note: Annotated[str, Field(max_length=300)] | None = None
    reservation_note: Annotated[str, Field(max_length=300)] | None = None
    host_name: Annotated[str, Field(max_length=80)] | None = None


class BrandedDetails(CommonDetails):
    presented_by: Sponsor | None = None
    activations: list[Activation] = Field(default_factory=list, max_length=8)
    promo_note: Annotated[str, Field(max_length=200)] | None = None
    giveaway_note: Annotated[str, Field(max_length=200)] | None = None


class PrivateGatheringDetails(CommonDetails):
    host_names: Annotated[str, Field(max_length=120)] | None = None
    occasion: Annotated[str, Field(max_length=80)] | None = None
    rsvp_note: Annotated[str, Field(max_length=300)] | None = None
    agenda: list[AgendaItem] = Field(default_factory=list, max_length=20)
    gift_note: Annotated[str, Field(max_length=300)] | None = None


class GenericDetails(CommonDetails):
    agenda: list[AgendaItem] = Field(default_factory=list, max_length=20)


_MODELS: dict[EventArchetype, type[CommonDetails]] = {
    "concert": ConcertDetails,
    "religious": ReligiousDetails,
    "sports_family": SportsFamilyDetails,
    "restaurant": RestaurantDetails,
    "private_gathering": PrivateGatheringDetails,
    "branded": BrandedDetails,
    "generic": GenericDetails,
}


def details_model(archetype: EventArchetype) -> type[CommonDetails]:
    return _MODELS[archetype]


def _dump(model: CommonDetails) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True, exclude_defaults=True)


def validate_details(archetype: EventArchetype, raw: object) -> dict[str, Any]:
    """Validate organiser input for ``archetype``; raises a 422 ``AppError``."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _invalid("archetype_details must be an object", [])
    try:
        model = details_model(archetype).model_validate(raw)
    except ValidationError as exc:
        fields = [".".join(str(part) for part in err["loc"]) for err in exc.errors()]
        raise _invalid("Invalid archetype details", fields) from exc
    dumped = _dump(model)
    if len(json.dumps(dumped, separators=(",", ":")).encode()) > MAX_DETAILS_BYTES:
        raise _invalid("archetype_details too large", [])
    return dumped


def _invalid(message: str, fields: list[str]) -> AppError:
    return AppError(
        code="invalid_archetype_details",
        message=message,
        http_status=422,
        details={
            "field": "archetype_details",
            "fields": fields[:20],
            "message_key": "vendor.events.errors.invalidArchetypeDetails",
        },
    )


def prune_details(archetype: EventArchetype, raw: object) -> dict[str, Any]:
    """Keep only keys the archetype understands (used when the archetype changes)."""
    if not isinstance(raw, dict):
        return {}
    allowed = set(details_model(archetype).model_fields)
    kept = {key: value for key, value in raw.items() if key in allowed}
    try:
        return validate_details(archetype, kept)
    except AppError:
        return {}


def read_details(archetype: EventArchetype, raw: object) -> dict[str, Any]:
    """Public-read path: never raise; unvalidated stored JSON degrades to ``{}``."""
    if not isinstance(raw, dict) or not raw:
        return {}
    try:
        return validate_details(archetype, raw)
    except AppError:
        return {}
