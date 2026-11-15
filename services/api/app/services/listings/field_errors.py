"""Field-level listing errors with distinct draft vs publish wording.

A draft is a private work-in-progress: it must save as long as it is
structurally valid. Category / release policy only applies when a listing goes
live, so those rejections are reported as ``listing_publish_blocked`` and name
the field to fix, while structural problems on a draft are
``listing_draft_invalid``. Both carry ``details.fields`` as
``[{"field", "code", "message"}]`` for the vendor UI to render next to inputs.
"""

from __future__ import annotations

from typing import Any, Literal

from app.errors import AppError

ListingIntent = Literal["draft", "publish"]

# (substring of the Postgres message, field, code, publish-only). Order matters:
# the first match wins. ``publish_only`` rules come from the activation branch of
# enforce_product_strategy_listing_policy and can never fire for a draft.
_DB_RULES: tuple[tuple[str, str, str, bool], ...] = (
    ("is not customer-released", "product_class", "class_not_released", True),
    ("category policy does not allow", "category_id", "category_policy_blocked", True),
    ("KYC tier is below", "vendor", "kyc_tier_too_low", True),
    ("active listing requires a category", "category_id", "category_required", True),
    ("require a canonical product", "product_id", "canonical_product_required", False),
    ("standalone category", "category_id", "category_required", False),
    ("listing-owned description", "description", "description_too_short", False),
    ("condition_detail_parent_check", "condition_detail", "condition_grade_mismatch", False),
    ("used_needs_notes_check", "defect_notes", "defect_notes_required", False),
    ("lead_time_check", "lead_time_days", "lead_time_invalid", False),
    ("class_e_fields_check", "vendor_capacity_per_week", "capacity_required", False),
    ("class_e_capacity_floor_check", "vendor_capacity_per_week", "capacity_too_low", False),
    ("capacity_only_class_e_check", "vendor_capacity_per_week", "capacity_not_allowed", False),
    ("standalone_title_check", "title_override", "title_required", False),
    ("standalone_class_check", "product_id", "standalone_required", False),
    ("fulfilment_options_check", "fulfilment_options", "fulfilment_options_invalid", False),
    ("compare_at", "compare_at_ngwee", "compare_at_too_low", False),
    ("active used listing", "evidence_images", "evidence_required", True),
)

_MESSAGES: dict[str, str] = {
    "class_not_released": "This product class is not open for public sale yet.",
    "category_policy_blocked": "This category does not allow that product class for live listings.",
    "kyc_tier_too_low": "Your verification level is below what this category requires to go live.",
    "category_required": "Choose a category.",
    "canonical_product_required": "Attach a catalogue product for this class.",
    "description_too_short": "Describe the item in at least 20 characters.",
    "condition_grade_mismatch": "Choose a grade that matches the condition.",
    "defect_notes_required": "Describe any wear or defects in at least 10 characters.",
    "lead_time_invalid": "Lead time must be between 1 and 365 days for made-to-order items.",
    "capacity_required": "Weekly capacity is required for made-to-order (Class E) items.",
    "capacity_too_low": "Weekly capacity must cover the minimum purchase quantity.",
    "capacity_not_allowed": "Weekly capacity only applies to Class E items.",
    "title_required": "Enter a title.",
    "standalone_required": "This class is a standalone offer, not attached to a catalogue product.",
    "fulfilment_options_invalid": "Choose at least one way to hand over this item.",
    "compare_at_too_low": "The compare-at price must be higher than the price.",
    "evidence_required": "Add at least one photo of the item before it goes live.",
}


def listing_issue(field: str, code: str, message: str | None = None) -> dict[str, str]:
    return {"field": field, "code": code, "message": message or _MESSAGES.get(code, code)}


def listing_field_error(
    *,
    intent: ListingIntent,
    fields: list[dict[str, str]],
    http_status: int = 422,
    message_key: str | None = None,
) -> AppError:
    code = "listing_publish_blocked" if intent == "publish" else "listing_draft_invalid"
    message = (
        "This listing cannot be published yet. Fix the highlighted fields."
        if intent == "publish"
        else "This draft cannot be saved yet. Fix the highlighted fields."
    )
    return AppError(
        code=code,
        message=message,
        http_status=http_status,
        details={
            "message_key": message_key
            or (
                "vendor.listings.errors.publishBlocked"
                if intent == "publish"
                else "vendor.listings.errors.draftInvalid"
            ),
            "intent": intent,
            "fields": fields,
        },
    )


def map_listing_db_error(exc: Exception, *, intent: ListingIntent) -> AppError | None:
    """Translate a Postgres check_violation into field-level issues, or None."""
    if getattr(exc, "code", None) != "23514":
        return None
    raw = " ".join(
        str(part)
        for part in (
            getattr(exc, "message", None),
            getattr(exc, "details", None),
            getattr(exc, "hint", None),
            exc,
        )
        if part
    )
    for needle, field, code, publish_only in _DB_RULES:
        if needle in raw:
            return listing_field_error(
                intent="publish" if publish_only else intent,
                fields=[listing_issue(field, code)],
            )
    return listing_field_error(
        intent=intent,
        fields=[
            listing_issue(
                "_form",
                "listing_rejected",
                "The database rejected this listing. Check the details and try again.",
            )
        ],
    )


def issues_from_validation_error(exc: Any) -> list[dict[str, str]]:
    """Field issues from a pydantic ValidationError raised by VendorListing."""
    issues: list[dict[str, str]] = []
    for error in exc.errors():
        ctx = error.get("ctx") or {}
        field = ctx.get("field") if isinstance(ctx, dict) else None
        if not isinstance(field, str):
            loc = [part for part in error.get("loc", ()) if isinstance(part, str)]
            field = loc[-1] if loc else "_form"
        code = ctx.get("code") if isinstance(ctx, dict) else None
        issues.append(
            listing_issue(
                field,
                str(code or error.get("type", "invalid")),
                str(error.get("msg", "Invalid value")).removeprefix("Value error, "),
            )
        )
    return issues
