"""Admin-controlled category presentation: icon, banner image and banner copy.

Rows live in ``public.category_presentations`` (service-role only). The public
read is cached (TTL cache + ``Cache-Control``) and busted on every admin write.
Media are Cloudinary public ids; copy is per-locale text with hard limits
(banner title 60 characters, banner description 160) enforced here and again by
the table's CHECK constraints.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.ttl_cache import get_cached_json, set_cached_json
from app.schemas.base import StrictModel
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

TABLE = "category_presentations"
PRESENTATION_COLUMNS = (
    "category_id, icon_public_id, banner_public_id, banner_title_i18n, "
    "banner_description_i18n, updated_at"
)
PRESENTATIONS_CACHE_KEY = "public:category-presentations:v1"
PRESENTATIONS_CACHE_TTL_SECONDS = 3600  # 1 hour; admin writes bust it.

MAX_BANNER_TITLE_CHARS = 60
MAX_BANNER_DESCRIPTION_CHARS = 160
LOCALE_KEYS = frozenset({"en", "bem", "nya", "fr", "zh"})
DEFAULT_LOCALE = "en"
PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9_./-]{1,255}$")

# PostgREST "relation does not exist" codes. Until the migration is pushed the
# public read degrades to "no presentations" instead of failing the page.
_MISSING_TABLE_MARKERS = ("PGRST205", "42P01")


def validate_public_id(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lstrip("/")
    if not cleaned:
        return None
    if not PUBLIC_ID_RE.fullmatch(cleaned) or ".." in cleaned:
        raise ValueError(f"{field} is not a valid Cloudinary public id")
    return cleaned


def validate_copy(copy: dict[str, str], *, field: str, max_chars: int) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for locale, text in copy.items():
        if locale not in LOCALE_KEYS:
            raise ValueError(f"{field}: unsupported locale {locale}")
        if not isinstance(text, str):
            raise ValueError(f"{field}: text must be a string")
        stripped = " ".join(text.split())
        if not stripped:
            # An empty field in the editor means "no text for this locale".
            continue
        if len(stripped) > max_chars:
            raise ValueError(f"{field}: {locale} must be at most {max_chars} characters")
        cleaned[locale] = stripped
    if cleaned and DEFAULT_LOCALE not in cleaned:
        raise ValueError(f"{field}: English (en) text is required when any locale is set")
    return cleaned


class CategoryPresentationUpsert(BaseModel):
    """Full replacement of one category's presentation (PUT semantics)."""

    model_config = {"extra": "forbid"}

    icon_public_id: str | None = None
    banner_public_id: str | None = None
    banner_title_i18n: dict[str, str] = Field(default_factory=dict)
    banner_description_i18n: dict[str, str] = Field(default_factory=dict)

    @field_validator("icon_public_id")
    @classmethod
    def _icon(cls, value: str | None) -> str | None:
        return validate_public_id(value, field="icon_public_id")

    @field_validator("banner_public_id")
    @classmethod
    def _banner(cls, value: str | None) -> str | None:
        return validate_public_id(value, field="banner_public_id")

    @field_validator("banner_title_i18n")
    @classmethod
    def _title(cls, value: dict[str, str]) -> dict[str, str]:
        return validate_copy(value, field="banner_title_i18n", max_chars=MAX_BANNER_TITLE_CHARS)

    @field_validator("banner_description_i18n")
    @classmethod
    def _description(cls, value: dict[str, str]) -> dict[str, str]:
        return validate_copy(
            value, field="banner_description_i18n", max_chars=MAX_BANNER_DESCRIPTION_CHARS
        )

    @model_validator(mode="after")
    def _description_needs_title(self) -> CategoryPresentationUpsert:
        if self.banner_description_i18n and not self.banner_title_i18n:
            raise ValueError("banner_description_i18n requires a banner title")
        return self

    def is_empty(self) -> bool:
        return not (
            self.icon_public_id
            or self.banner_public_id
            or self.banner_title_i18n
            or self.banner_description_i18n
        )


class CategoryPresentationOut(StrictModel):
    category_id: str
    slug: str
    icon_public_id: str | None = None
    banner_public_id: str | None = None
    banner_title_i18n: dict[str, str] = Field(default_factory=dict)
    banner_description_i18n: dict[str, str] = Field(default_factory=dict)
    updated_at: str | None = None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _is_missing_table(exc: Exception) -> bool:
    text = f"{getattr(exc, 'code', '')} {exc}"
    return any(marker in text for marker in _MISSING_TABLE_MARKERS)


def _copy_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(locale): text
        for locale, text in value.items()
        if locale in LOCALE_KEYS and isinstance(text, str) and text.strip()
    }


def row_to_presentation(row: dict[str, Any], slug: str) -> CategoryPresentationOut:
    updated_at = row.get("updated_at")
    return CategoryPresentationOut(
        category_id=str(row.get("category_id")),
        slug=slug,
        icon_public_id=row.get("icon_public_id") or None,
        banner_public_id=row.get("banner_public_id") or None,
        banner_title_i18n=_copy_map(row.get("banner_title_i18n")),
        banner_description_i18n=_copy_map(row.get("banner_description_i18n")),
        updated_at=str(updated_at) if updated_at else None,
    )


def load_presentations(client: Any, *, public_only: bool) -> list[CategoryPresentationOut]:
    """Join presentations to category slugs; public reads skip prohibited categories."""
    try:
        rows = _rows(client.table(TABLE).select(PRESENTATION_COLUMNS).execute())
    except Exception as exc:
        if _is_missing_table(exc):
            logger.warning("category_presentations table missing; migration not applied yet")
            return []
        raise
    if not rows:
        return []
    category_query = client.table("categories").select("id, slug, prohibited")
    categories = _rows(category_query.execute())
    slugs: dict[str, str] = {}
    for category in categories:
        if public_only and category.get("prohibited"):
            continue
        slug = category.get("slug")
        if category.get("id") and isinstance(slug, str):
            slugs[str(category["id"])] = slug
    result: list[CategoryPresentationOut] = []
    for row in rows:
        slug = slugs.get(str(row.get("category_id")))
        if slug is None:
            continue
        result.append(row_to_presentation(row, slug))
    result.sort(key=lambda item: item.slug)
    return result


def list_public_presentations(
    client: Any,
    *,
    use_cache: bool = True,
    store: Any | None = None,
) -> list[CategoryPresentationOut]:
    if use_cache:
        cached = get_cached_json(PRESENTATIONS_CACHE_KEY, store=store)
        if isinstance(cached, list):
            try:
                return [CategoryPresentationOut.model_validate(item) for item in cached]
            except Exception:
                pass

    presentations = load_presentations(client, public_only=True)
    if use_cache:
        set_cached_json(
            PRESENTATIONS_CACHE_KEY,
            [item.model_dump(mode="json") for item in presentations],
            ttl_seconds=PRESENTATIONS_CACHE_TTL_SECONDS,
            store=store,
        )
    return presentations


def invalidate_public_presentations_cache(store: Any | None = None) -> None:
    """Best-effort bust after an admin write: the next public read reloads from the DB."""
    try:
        set_cached_json(PRESENTATIONS_CACHE_KEY, None, ttl_seconds=1, store=store)
    except Exception:  # pragma: no cover - cache is best-effort
        logger.warning("category presentation cache bust failed", exc_info=True)
