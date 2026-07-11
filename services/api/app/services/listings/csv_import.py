from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from app.services.kyc.caps import LISTING_COUNT_STATUSES, VendorCapLimits
from app.services.moderation.prohibited import screen_listing

ListingCondition = Literal["new", "refurbished"]
StockMode = Literal["tracked", "always_available"]
ListingStatus = Literal["draft", "active", "paused"]

MAX_CSV_BYTES = 512_000
MAX_CSV_ROWS = 500

REQUIRED_COLUMNS = frozenset(
    {
        "sku",
        "title",
        "price_ngwee",
        "stock_mode",
        "condition",
    }
)

OPTIONAL_COLUMNS = frozenset(
    {
        "stock_qty",
        "wholesale",
        "moq",
        "price_tiers",
        "returnable",
        "return_window_hours",
        "status",
        "vendor_id",
    }
)

ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


class SupabaseTableClient(Protocol):
    def table(self, name: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class PriceTierRow:
    min_qty: int
    price_ngwee: int


@dataclass(frozen=True, slots=True)
class ParsedListingRow:
    sku: str
    title: str
    price_ngwee: int
    stock_mode: StockMode
    stock_qty: int | None
    condition: ListingCondition
    wholesale: bool
    moq: int
    price_tiers: list[PriceTierRow] | None
    returnable: bool
    return_window_hours: int | None
    status: ListingStatus


@dataclass(frozen=True, slots=True)
class RowImportResult:
    row: int
    ok: bool
    errors: list[str]
    listing_id: str | None = None


@dataclass(frozen=True, slots=True)
class ImportSummary:
    accepted: int
    rejected: int
    rows: list[RowImportResult]


def is_valid_price_tiers(tiers: list[PriceTierRow]) -> list[str]:
    """Inline tier validation (mirrors vendor_listings._validate_price_tiers_ordered)."""
    if not tiers:
        return []
    errors: list[str] = []
    ordered = sorted(tiers, key=lambda tier: tier.min_qty)
    prev_qty = 0
    prev_price: int | None = None
    for tier in ordered:
        if tier.min_qty <= prev_qty:
            errors.append("price_tiers must have strictly ascending min_qty")
            break
        if prev_price is not None and tier.price_ngwee >= prev_price:
            errors.append("price_tiers must have strictly descending unit prices")
            break
        if tier.min_qty < 1:
            errors.append("price_tiers min_qty must be at least 1")
            break
        if tier.price_ngwee <= 0:
            errors.append("price_tiers price_ngwee must be greater than zero")
            break
        prev_qty = tier.min_qty
        prev_price = tier.price_ngwee
    return errors


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _parse_int_field(value: str | None, *, field: str, minimum: int | None = None) -> int:
    if value is None or not str(value).strip():
        raise ValueError(f"{field} is required")
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return parsed


def _parse_optional_int(
    value: str | None,
    *,
    field: str,
    minimum: int | None = None,
) -> int | None:
    if value is None or not str(value).strip():
        return None
    return _parse_int_field(value, field=field, minimum=minimum)


def _parse_price_tiers(raw: str | None) -> list[PriceTierRow] | None:
    if raw is None or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("price_tiers must be valid JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("price_tiers must be a JSON array")
    tiers: list[PriceTierRow] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"price_tiers[{index}] must be an object")
        min_qty = _parse_int_field(str(item.get("min_qty", "")), field="min_qty", minimum=1)
        price_ngwee = _parse_int_field(
            str(item.get("price_ngwee", "")),
            field="price_ngwee",
            minimum=1,
        )
        tiers.append(PriceTierRow(min_qty=min_qty, price_ngwee=price_ngwee))
    return tiers


def validate_row_dict(
    row_number: int,
    raw: dict[str, str],
    *,
    kyc_tier: int,
) -> tuple[ParsedListingRow | None, list[str]]:
    errors: list[str] = []
    extra_keys = set(raw.keys()) - ALL_COLUMNS
    if extra_keys:
        errors.append(f"unknown columns: {', '.join(sorted(extra_keys))}")

    for column in REQUIRED_COLUMNS:
        if not str(raw.get(column, "")).strip():
            errors.append(f"missing required column: {column}")

    if errors:
        return None, errors

    sku = str(raw["sku"]).strip()
    title = str(raw["title"]).strip()
    if not sku:
        errors.append("sku must not be empty")
    if not title:
        errors.append("title must not be empty")

    try:
        price_ngwee = _parse_int_field(raw.get("price_ngwee"), field="price_ngwee", minimum=1)
    except ValueError as exc:
        errors.append(str(exc))
        price_ngwee = 0

    stock_mode_raw = str(raw["stock_mode"]).strip().lower()
    if stock_mode_raw not in {"tracked", "always_available"}:
        errors.append("stock_mode must be tracked or always_available")
        stock_mode: StockMode = "tracked"
    else:
        stock_mode = cast(StockMode, stock_mode_raw)

    stock_qty: int | None = None
    if stock_mode == "tracked":
        try:
            stock_qty = _parse_int_field(raw.get("stock_qty"), field="stock_qty", minimum=0)
        except ValueError as exc:
            errors.append(str(exc))
    elif str(raw.get("stock_qty", "")).strip():
        try:
            stock_qty = _parse_optional_int(raw.get("stock_qty"), field="stock_qty", minimum=0)
        except ValueError as exc:
            errors.append(str(exc))

    condition_raw = str(raw["condition"]).strip().lower()
    if condition_raw not in {"new", "refurbished"}:
        errors.append("condition must be new or refurbished")
        condition: ListingCondition = "new"
    else:
        condition = cast(ListingCondition, condition_raw)

    try:
        wholesale = _parse_bool(raw.get("wholesale"), default=False)
    except ValueError as exc:
        errors.append(str(exc))
        wholesale = False

    try:
        moq = _parse_int_field(raw.get("moq") or "1", field="moq", minimum=1)
    except ValueError as exc:
        errors.append(str(exc))
        moq = 1

    try:
        price_tiers = _parse_price_tiers(raw.get("price_tiers"))
    except ValueError as exc:
        errors.append(str(exc))
        price_tiers = None

    try:
        returnable = _parse_bool(raw.get("returnable"), default=False)
    except ValueError as exc:
        errors.append(str(exc))
        returnable = False

    return_window_hours: int | None = None
    if returnable:
        try:
            return_window_hours = _parse_int_field(
                raw.get("return_window_hours"),
                field="return_window_hours",
                minimum=1,
            )
        except ValueError as exc:
            errors.append(str(exc))
    elif str(raw.get("return_window_hours", "")).strip():
        try:
            return_window_hours = _parse_optional_int(
                raw.get("return_window_hours"),
                field="return_window_hours",
                minimum=1,
            )
        except ValueError as exc:
            errors.append(str(exc))

    status_raw = str(raw.get("status") or "active").strip().lower()
    if status_raw not in {"draft", "active", "paused"}:
        errors.append("status must be draft, active, or paused")
        status: ListingStatus = "active"
    else:
        status = cast(ListingStatus, status_raw)

    if wholesale and kyc_tier < 2:
        errors.append("wholesale requires T2 verification or higher")
    if wholesale and not price_tiers:
        errors.append("wholesale listings require price_tiers")

    if price_tiers:
        errors.extend(is_valid_price_tiers(price_tiers))

    if errors:
        return None, errors

    return (
        ParsedListingRow(
            sku=sku,
            title=title,
            price_ngwee=price_ngwee,
            stock_mode=stock_mode,
            stock_qty=stock_qty,
            condition=condition,
            wholesale=wholesale,
            moq=moq,
            price_tiers=price_tiers,
            returnable=returnable,
            return_window_hours=return_window_hours,
            status=status,
        ),
        [],
    )


def parse_csv_text(csv_text: str) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    if not csv_text.strip():
        return [], ["CSV file is empty"]

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return [], ["CSV header row is missing"]

    normalized_headers = [name.strip() for name in reader.fieldnames if name]
    missing = REQUIRED_COLUMNS - set(normalized_headers)
    if missing:
        return [], [f"missing required headers: {', '.join(sorted(missing))}"]

    rows: list[dict[str, str]] = []
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > MAX_CSV_ROWS:
            errors.append(f"row limit exceeded ({MAX_CSV_ROWS} data rows maximum)")
            break
        row = {
            (key or "").strip(): (value or "").strip()
            for key, value in raw_row.items()
            if key is not None
        }
        if not any(row.values()):
            continue
        rows.append(row)

    return rows, errors


def build_template_csv() -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=sorted(ALL_COLUMNS - {"vendor_id"}),
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerow(
        {
            "sku": "TOM-001",
            "title": "Fresh tomatoes per kg",
            "price_ngwee": "2500",
            "stock_mode": "tracked",
            "stock_qty": "50",
            "condition": "new",
            "wholesale": "false",
            "moq": "1",
            "status": "active",
        }
    )
    writer.writerow(
        {
            "sku": "RICE-10KG",
            "title": "White rice 10kg bag",
            "price_ngwee": "18500",
            "stock_mode": "tracked",
            "stock_qty": "20",
            "condition": "new",
            "wholesale": "true",
            "moq": "5",
            "price_tiers": '[{"min_qty":5,"price_ngwee":17500},{"min_qty":20,"price_ngwee":16000}]',
            "status": "active",
        }
    )
    return buffer.getvalue()


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def _load_existing_sku_map(
    client: SupabaseTableClient,
    vendor_id: str,
) -> dict[str, dict[str, Any]]:
    response = (
        client.table("vendor_listings")
        .select("id, sku, status")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    sku_map: dict[str, dict[str, Any]] = {}
    for row in _rows(response):
        sku = row.get("sku")
        if isinstance(sku, str) and sku:
            sku_map[sku] = row
    return sku_map


def _serialize_price_tiers(tiers: list[PriceTierRow] | None) -> list[dict[str, int]] | None:
    if not tiers:
        return None
    return [{"min_qty": tier.min_qty, "price_ngwee": tier.price_ngwee} for tier in tiers]


def _listing_payload(vendor_id: str, parsed: ParsedListingRow) -> dict[str, Any]:
    return {
        "vendor_id": vendor_id,
        "product_id": None,
        "sku": parsed.sku,
        "title_override": parsed.title,
        "price_ngwee": parsed.price_ngwee,
        "condition": parsed.condition,
        "stock_mode": parsed.stock_mode,
        "stock_qty": parsed.stock_qty,
        "wholesale": parsed.wholesale,
        "price_tiers": _serialize_price_tiers(parsed.price_tiers),
        "moq": parsed.moq,
        "returnable": parsed.returnable,
        "return_window_hours": parsed.return_window_hours,
        "status": parsed.status,
    }


def _counts_toward_cap(status: str) -> bool:
    return status in LISTING_COUNT_STATUSES


def import_listing_rows(
    client: SupabaseTableClient,
    *,
    vendor_id: str,
    limits: VendorCapLimits,
    rows: list[dict[str, str]],
) -> ImportSummary:
    results: list[RowImportResult] = []
    accepted = 0
    rejected = 0

    sku_map = _load_existing_sku_map(client, vendor_id)
    cap_slots_used = limits.listing_count
    max_listings = limits.quota.max_listings
    seen_skus_in_file: set[str] = set()

    for index, raw_row in enumerate(rows, start=1):
        parsed, validation_errors = validate_row_dict(
            index,
            raw_row,
            kyc_tier=limits.kyc_tier,
        )
        if validation_errors:
            rejected += 1
            results.append(RowImportResult(row=index, ok=False, errors=validation_errors))
            continue

        assert parsed is not None
        sku = parsed.sku

        guard = screen_listing(title=parsed.title)
        if not guard.allowed:
            rejected += 1
            results.append(
                RowImportResult(
                    row=index,
                    ok=False,
                    errors=[f"prohibited listing blocked ({guard.reason}): {guard.matched}"],
                )
            )
            continue

        if sku in seen_skus_in_file:
            rejected += 1
            results.append(
                RowImportResult(
                    row=index,
                    ok=False,
                    errors=[f"duplicate sku in file: {sku}"],
                )
            )
            continue
        seen_skus_in_file.add(sku)

        existing = sku_map.get(sku)
        is_new = existing is None
        if is_new and _counts_toward_cap(parsed.status):
            if cap_slots_used >= max_listings:
                rejected += 1
                results.append(
                    RowImportResult(
                        row=index,
                        ok=False,
                        errors=[
                            f"listing cap exceeded (max {max_listings} for tier T{limits.kyc_tier})"
                        ],
                    )
                )
                continue
            cap_slots_used += 1

        payload = _listing_payload(vendor_id, parsed)

        try:
            if existing is not None:
                listing_id = str(existing["id"])
                update_response = (
                    client.table("vendor_listings")
                    .update(payload)
                    .eq("id", listing_id)
                    .eq("vendor_id", vendor_id)
                    .execute()
                )
                updated = _single_row(update_response)
                if updated is None:
                    raise RuntimeError("update returned no row")
            else:
                insert_response = client.table("vendor_listings").insert(payload).execute()
                created = _single_row(insert_response)
                if created is None:
                    raise RuntimeError("insert returned no row")
                listing_id = str(created["id"])
                sku_map[sku] = created
        except Exception as exc:  # noqa: BLE001 — row-level failure isolation
            rejected += 1
            results.append(
                RowImportResult(
                    row=index,
                    ok=False,
                    errors=[f"database error: {exc}"],
                )
            )
            if is_new and _counts_toward_cap(parsed.status):
                cap_slots_used -= 1
            continue

        accepted += 1
        results.append(
            RowImportResult(row=index, ok=True, errors=[], listing_id=listing_id)
        )

    return ImportSummary(accepted=accepted, rejected=rejected, rows=results)


def import_csv_bytes(
    client: SupabaseTableClient,
    *,
    vendor_id: str,
    limits: VendorCapLimits,
    csv_bytes: bytes,
) -> ImportSummary:
    if len(csv_bytes) > MAX_CSV_BYTES:
        return ImportSummary(
            accepted=0,
            rejected=0,
            rows=[
                RowImportResult(
                    row=0,
                    ok=False,
                    errors=[f"CSV exceeds maximum size of {MAX_CSV_BYTES} bytes"],
                )
            ],
        )

    try:
        csv_text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ImportSummary(
            accepted=0,
            rejected=0,
            rows=[RowImportResult(row=0, ok=False, errors=["CSV must be UTF-8 encoded"])],
        )

    parsed_rows, parse_errors = parse_csv_text(csv_text)
    if parse_errors:
        return ImportSummary(
            accepted=0,
            rejected=0,
            rows=[RowImportResult(row=0, ok=False, errors=parse_errors)],
        )

    return import_listing_rows(
        client,
        vendor_id=vendor_id,
        limits=limits,
        rows=parsed_rows,
    )
