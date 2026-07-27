"""M18-P04 — the constraint surface for intake draft extraction (D35).

This module is the *only* shape a model may return. There is no free-form
model-output path anywhere in the intake lane: an extractor's result is either a
value that validates against these models, or it is discarded.

Money is **integer ngwee** throughout. A price is parsed with ``Decimal`` and
never touches a float.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

# K1,000,000.00 — an intake draft above this is a data error, not a product.
MAX_PRICE_NGWEE: Final = 100_000_000_00
MAX_QUANTITY: Final = 1_000_000
MAX_TITLE_LEN: Final = 200
MAX_DESCRIPTION_LEN: Final = 4_000


class FieldSource(StrEnum):
    """Where a draft field's value came from. Rendered to every human reviewer."""

    VENDOR_TYPED = "vendor_typed"
    RULE = "rule"
    MODEL = "model"


class PricingMode(StrEnum):
    FIXED = "fixed"
    NEGOTIABLE = "negotiable"
    TIERED = "tiered"


class StockMode(StrEnum):
    TRACKED = "tracked"
    MADE_TO_ORDER = "made_to_order"
    ALWAYS = "always"


class Condition(StrEnum):
    NEW = "new"
    REFURBISHED = "refurbished"
    USED = "used"


class DraftFields(BaseModel):
    """The extractable product fields.

    ``extra="forbid"`` matters: a model that invents a field fails validation
    outright rather than having the surplus silently dropped, so we always know
    when output did not match the contract.
    """

    model_config = ConfigDict(extra="forbid", strict=False)

    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    category_slug: str | None = Field(default=None, max_length=120)
    price_ngwee: int | None = Field(default=None, ge=0, le=MAX_PRICE_NGWEE)
    pricing_mode: PricingMode | None = None
    quantity: int | None = Field(default=None, ge=0, le=MAX_QUANTITY)
    stock_mode: StockMode | None = None
    sale_unit: str | None = Field(default=None, max_length=40)
    condition: Condition | None = None
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LEN)


# Fields a draft must have before a vendor can be asked to review it.
REQUIRED_FOR_REVIEW: Final[tuple[str, ...]] = (
    "title",
    "category_slug",
    "price_ngwee",
    "condition",
)


class FieldProvenance(BaseModel):
    """Per-field origin, persisted alongside the draft."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    source: FieldSource
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    model_ref: str | None = None


class OpenQuestion(BaseModel):
    """A follow-up recorded as DATA on the intake record.

    The lane is strictly inbound-only: this is never sent to the vendor. The
    vendor app (M18-P05) renders ``key`` from its own i18n namespace with
    ``params``, so no user-facing copy lives in the API.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    field_name: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """What an extraction pass produced, with its provenance and questions."""

    model_config = ConfigDict(extra="forbid")

    fields: DraftFields
    provenance: list[FieldProvenance] = Field(default_factory=list)
    questions: list[OpenQuestion] = Field(default_factory=list)
    prohibited_reason: str | None = None

    @property
    def blocked(self) -> bool:
        return self.prohibited_reason is not None
