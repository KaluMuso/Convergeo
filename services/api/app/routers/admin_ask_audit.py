"""Admin: Ask Vergeo answer log and auditor findings (read-only).

Lists every logged answer with the auditor's verdict so an admin can see exactly what a
customer was told, which cited item or price looked wrong, and open the listing and the
vendor to investigate and make contact. Customer identity is never returned (only
whether the asker was signed in), and nothing here writes: findings are produced by the
background auditor (``app.services.ask.audit``).

Mounted on the shared ``/admin`` router, so it is gated to ``admin`` / ``superadmin``
like the other unrestricted-only boards (not delegated to ``rbac_*`` roles).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from app.deps import get_supabase_client
from app.routers.admin_base import router as admin_router
from app.services.ask.citations import route_path
from app.services.ask.enrich import rows_of
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

router = APIRouter(prefix="/ask-audit", tags=["admin-ask-audit"])

MAX_PAGE = 100
_ANSWER_COLUMNS = (
    "id,created_at,query,answer_text,model,source,intent,cached,refused,locale,user_id,"
    "citations,audit_status,audit_severity,audited_at"
)
_FINDING_COLUMNS = "id,answer_id,rule,severity,reason,entity_kind,entity_id,vendor_id,details"


class CitedItemOut(BaseModel):
    kind: str
    id: str
    title: str
    price_ngwee: int | None = None
    price_max_ngwee: int | None = None
    href: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    vendor_href: str | None = None


class FindingOut(BaseModel):
    id: str
    rule: str
    severity: Literal["info", "warning", "critical"]
    reason: str
    entity_kind: str | None = None
    entity_id: str | None = None
    entity_href: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    vendor_href: str | None = None
    details: dict[str, Any]


class AskAnswerOut(BaseModel):
    id: str
    created_at: datetime
    query: str
    answer_text: str
    model: str | None
    source: str
    intent: str | None
    cached: bool
    refused: bool
    locale: str | None
    asker: Literal["customer", "guest"]
    audit_status: Literal["pending", "passed", "flagged", "error"]
    audit_severity: Literal["info", "warning", "critical"] | None
    audited_at: datetime | None
    citations: list[CitedItemOut]
    findings: list[FindingOut]


class AskAnswerPageOut(BaseModel):
    items: list[AskAnswerOut]
    next_before: datetime | None
    next_before_id: str | None = None


def _clean_slug(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _vendor_lookup(client: Any, vendor_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not vendor_ids:
        return {}
    rows = rows_of(
        client.table("vendors")
        .select("id,slug,display_name")
        .in_("id", sorted(vendor_ids))
        .execute()
    )
    return {str(row["id"]): row for row in rows if row.get("id")}


def _vendor_fields(vendors: dict[str, dict[str, Any]], vendor_id: str | None) -> dict[str, Any]:
    vendor = vendors.get(vendor_id) if vendor_id else None
    slug = _clean_slug(vendor.get("slug")) if vendor else None
    name = vendor.get("display_name") if vendor else None
    return {
        "vendor_id": vendor_id,
        "vendor_name": name.strip() if isinstance(name, str) and name.strip() else None,
        "vendor_href": route_path("vendor", vendor_id, slug) if vendor_id and slug else None,
    }


def _cited_items(entries: Any, vendors: dict[str, dict[str, Any]]) -> list[CitedItemOut]:
    out: list[CitedItemOut] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("kind"):
            continue
        vendor_id = str(entry["vendor_id"]) if entry.get("vendor_id") else None
        fields = _vendor_fields(vendors, vendor_id)
        out.append(
            CitedItemOut(
                kind=str(entry["kind"]),
                id=str(entry["id"]),
                title=str(entry.get("title") or ""),
                price_ngwee=entry.get("price_ngwee"),
                price_max_ngwee=entry.get("price_max_ngwee"),
                href=route_path(str(entry["kind"]), str(entry["id"]), entry.get("slug")),
                **fields,
            )
        )
    return out


@router.get("", response_model=AskAnswerPageOut)
def list_ask_answers(
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    flagged_only: Annotated[bool, Query()] = False,
    severity: Annotated[Literal["warning", "critical"] | None, Query()] = None,
    before: Annotated[datetime | None, Query()] = None,
    before_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
) -> AskAnswerPageOut:
    client: Any = service.client
    query = (
        client.table("ask_answers")
        .select(_ANSWER_COLUMNS)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .limit(limit + 1)
    )
    if flagged_only:
        query = query.eq("audit_status", "flagged")
    if severity is not None:
        query = query.eq("audit_severity", severity)
    if before is not None:
        before_iso = before.isoformat()
        if before_id is not None:
            query = query.or_(
                f"created_at.lt.{before_iso},and(created_at.eq.{before_iso},id.lt.{before_id})"
            )
        else:
            query = query.lt("created_at", before_iso)

    rows = rows_of(query.execute())
    page = rows[:limit]

    findings_by_answer: dict[str, list[dict[str, Any]]] = {}
    if page:
        for finding in rows_of(
            client.table("ask_answer_findings")
            .select(_FINDING_COLUMNS)
            .in_("answer_id", [str(r["id"]) for r in page])
            .order("created_at")
            .execute()
        ):
            findings_by_answer.setdefault(str(finding["answer_id"]), []).append(finding)

    vendor_ids: set[str] = set()
    for row in page:
        for entry in row.get("citations") or []:
            if isinstance(entry, dict) and entry.get("vendor_id"):
                vendor_ids.add(str(entry["vendor_id"]))
        for finding in findings_by_answer.get(str(row["id"]), []):
            if finding.get("vendor_id"):
                vendor_ids.add(str(finding["vendor_id"]))
    vendors = _vendor_lookup(client, vendor_ids)

    items: list[AskAnswerOut] = []
    for row in page:
        answer_id = str(row["id"])
        slug_by_entity = {
            (str(e.get("kind")), str(e.get("id"))): e.get("slug")
            for e in row.get("citations") or []
            if isinstance(e, dict)
        }
        findings = []
        for finding in findings_by_answer.get(answer_id, []):
            kind = finding.get("entity_kind")
            entity_id = str(finding["entity_id"]) if finding.get("entity_id") else None
            vendor_id = str(finding["vendor_id"]) if finding.get("vendor_id") else None
            findings.append(
                FindingOut(
                    id=str(finding["id"]),
                    rule=str(finding["rule"]),
                    severity=finding["severity"],
                    reason=str(finding["reason"]),
                    entity_kind=kind,
                    entity_id=entity_id,
                    entity_href=(
                        route_path(kind, entity_id, slug_by_entity.get((kind, entity_id)))
                        if kind and entity_id
                        else None
                    ),
                    details=finding.get("details") or {},
                    **{
                        k: v
                        for k, v in _vendor_fields(vendors, vendor_id).items()
                        if k != "vendor_id"
                    },
                    vendor_id=vendor_id,
                )
            )
        items.append(
            AskAnswerOut(
                id=answer_id,
                created_at=row["created_at"],
                query=str(row.get("query") or ""),
                answer_text=str(row.get("answer_text") or ""),
                model=row.get("model"),
                source=str(row.get("source") or "ai"),
                intent=row.get("intent"),
                cached=bool(row.get("cached")),
                refused=bool(row.get("refused")),
                locale=row.get("locale"),
                asker="customer" if row.get("user_id") else "guest",
                audit_status=row.get("audit_status") or "pending",
                audit_severity=row.get("audit_severity"),
                audited_at=row.get("audited_at"),
                citations=_cited_items(row.get("citations"), vendors),
                findings=findings,
            )
        )
    next_before = items[-1].created_at if len(rows) > limit and items else None
    return AskAnswerPageOut(
        items=items,
        next_before=next_before,
        next_before_id=items[-1].id if next_before is not None else None,
    )


admin_router.include_router(router)
