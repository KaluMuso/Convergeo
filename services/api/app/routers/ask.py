from __future__ import annotations

import importlib
import logging
from datetime import timedelta
from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.analytics.search_log import log_ask_query
from app.services.ask.cache import cache_lookup, cache_write, normalize_query
from app.services.ask.citations import CitationRef, ValidatedAnswer, validate_citations
from app.services.ask.faq import FaqRef
from app.services.ask.filters import extract_filters
from app.services.ask.intents import (
    OrderRef,
    WorkflowResult,
    WorkflowRetriever,
    fallback_results,
    run_workflow,
)
from app.services.ask.prompt import build_prompt, call_answer_model
from app.services.ask.retrieve import top_k
from app.services.ask.spend import tokens_to_usd_micros
from app.settings import get_settings
from fastapi import APIRouter, Depends, Request
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["ask"])

REFUSAL_TEXT = "I couldn't find that on Vergeo5."
REFUSAL_MESSAGE_KEY = "ai.answer.not_found"
RATE_LIMIT_MESSAGE_KEY = "ai.answer.rate_limited"

# Friendly notes for the no-AI fallback (ranked search results + FAQ matches).
FALLBACK_AI_UNAVAILABLE_KEY = "ai.fallback.aiUnavailable"
FALLBACK_AI_PAUSED_KEY = "ai.fallback.aiPaused"
FALLBACK_TEXT = "Here are the closest matches on Vergeo5."

# Quota / kill-switch errors degrade to the fallback instead of an error banner.
_DEGRADE_TO_FALLBACK_CODES = frozenset(
    {
        "ai_quota_guest_exceeded",
        "ai_quota_daily_exceeded",
        "ai_quota_monthly_exceeded",
        "ai_quota_exceeded",
        "ai_quota_kill_switch",
    }
)

ASK_RATE_LIMIT_PER_MINUTE = 30
QUOTA_RATE_LIMIT_PER_MINUTE = 60

AskSource = Literal["ai", "workflow", "fallback"]


class AskRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    # Optional device location for "near me" — used for this request only, never stored.
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class AskQuota(StrictModel):
    tier: str
    daily_limit: int
    used: int
    remaining: int


class AskResponse(StrictModel):
    query: str
    answer: str
    citations: list[CitationRef]
    cached: bool = False
    refused: bool = False
    message_key: str | None = None
    # --- Ask Vergeo upgrade (all additive; older clients ignore them) ---
    source: AskSource = "ai"
    intent: str | None = None
    # Workflow answers are i18n keys + params so the UI renders the viewer's locale.
    answer_key: str | None = None
    answer_params: dict[str, str | int] = Field(default_factory=dict)
    # Friendly note (fallback reason / quota reached) and optional signup nudge.
    notice_key: str | None = None
    signup_prompt_key: str | None = None
    faq: list[FaqRef] = Field(default_factory=list)
    orders: list[OrderRef] = Field(default_factory=list)
    needs_location: bool = False
    sign_in_required: bool = False
    quota: AskQuota | None = None


# ---------------------------------------------------------------------------
# Quota hooks (imported lazily so the pipeline runs without the quota module)
# ---------------------------------------------------------------------------


def _quota_module() -> Any | None:
    try:
        return importlib.import_module("app.services.ask.quota")
    except ImportError:
        return None


def _optional_quota_check_and_reserve(
    *,
    client: Any,
    user_id: str | None,
    guest_key: str,
    question: str,
    client_ip: str | None = None,
) -> Any:
    quota = _quota_module()
    check_and_reserve = getattr(quota, "check_and_reserve", None) if quota else None
    if not callable(check_and_reserve):
        return None
    kwargs: dict[str, Any] = {
        "client": client,
        "user_id": user_id,
        "guest_key": guest_key,
        "question": question,
    }
    if client_ip is not None:
        kwargs["client_ip"] = client_ip
    return check_and_reserve(**kwargs)


def _optional_quota_record_answer(
    *, client: Any, user_id: str | None, guest_key: str, tokens: int, model: str
) -> None:
    quota = _quota_module()
    record_answer = getattr(quota, "record_answer", None) if quota else None
    if callable(record_answer):
        record_answer(
            client=client,
            user_id=user_id,
            guest_key=guest_key,
            tokens=tokens,
            model=model,
        )


def _optional_quota_release(*, client: Any, reservation: Any) -> None:
    """Best-effort: give the slot back when the model never answered."""
    quota = _quota_module()
    release = getattr(quota, "release_reservation", None) if quota else None
    if reservation is None or not callable(release):
        return
    try:
        release(client=client, reservation=reservation)
    except Exception:  # noqa: BLE001 — releasing is best-effort
        logger.warning("Ask quota release failed (swallowed)", exc_info=True)


def _quota_from_status(status: Any) -> AskQuota | None:
    if status is None:
        return None
    try:
        return AskQuota(
            tier=str(status.tier),
            daily_limit=int(status.daily_limit),
            used=int(status.used),
            remaining=int(status.remaining),
        )
    except Exception:  # noqa: BLE001 — quota display must never break Ask
        return None


def _optional_quota_status(
    *, client: Any, user_id: str | None, guest_key: str, client_ip: str | None
) -> AskQuota | None:
    """Best-effort remaining-quota read for responses that did not reserve a slot."""
    quota = _quota_module()
    status_fn = getattr(quota, "quota_status", None) if quota else None
    if not callable(status_fn):
        return None
    try:
        status = status_fn(client=client, user_id=user_id, guest_key=guest_key, client_ip=client_ip)
    except Exception:  # noqa: BLE001 — quota display must never break Ask
        logger.debug("Ask quota status lookup failed (swallowed)", exc_info=True)
        return None
    return _quota_from_status(status)


def _quota_from_error_details(details: dict[str, Any] | None) -> AskQuota | None:
    if not details:
        return None
    tier = details.get("tier")
    limit = details.get("daily_limit")
    if not isinstance(tier, str) or not isinstance(limit, int) or isinstance(limit, bool):
        return None
    used = details.get("used")
    return AskQuota(
        tier=tier,
        daily_limit=limit,
        used=used if isinstance(used, int) and not isinstance(used, bool) else limit,
        remaining=0,
    )


def _log_ask_analytics(
    *,
    client: Any,
    query: str,
    user_id: str | None,
    tokens: int,
    model: str,
    zero_result: bool,
) -> None:
    """Fire-and-forget Ask analytics: server operational log, anonymized, consent-independent.

    Records the Ask query (normalized term only, via ``log_ask_query``) plus its model
    spend in micro-USD so ``ask_cost_by_day`` and the $15/mo cap have a per-day data
    source. Spend is derived with the same ``tokens_to_usd_micros`` the kill-switch uses,
    so this log agrees with ``ask_spend_monthly``. Never raises into the Ask request.
    """
    try:
        usd_micros = tokens_to_usd_micros(tokens=tokens, model=model, client=client)
    except Exception:  # noqa: BLE001 — analytics must never break Ask
        logger.debug("ask usd_micros derivation failed (swallowed)", exc_info=True)
        usd_micros = 0
    log_ask_query(
        term=query,
        usd_micros=usd_micros,
        zero_result=zero_result,
        user_id=user_id,
    )


async def _optional_current_user(request: Request) -> CurrentUser | None:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return await get_current_user(request, get_settings())


def _rate_limit(request: Request, service_client: Any, *, key_prefix: str, limit: int) -> None:
    # Single manifest scope (``ask_ip``, rate_counters_scope_check); routes are
    # separated by key prefix so the quota poll cannot eat the ask budget.
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope="ask_ip",
        key=f"{key_prefix}{ip}",
        window=timedelta(minutes=1),
        limit=limit,
        client=service_client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key=RATE_LIMIT_MESSAGE_KEY,
            message="Too many Ask Vergeo requests",
        )


def _rate_limit_ask(request: Request, service_client: Any) -> None:
    _rate_limit(request, service_client, key_prefix="", limit=ASK_RATE_LIMIT_PER_MINUTE)


def _guest_key(request: Request) -> str:
    device_id = request.headers.get("x-device-id", "").strip()
    if device_id:
        return f"device:{device_id[:128]}"
    return f"ip:{get_client_ip(request)}"


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _refusal_response(query: str) -> AskResponse:
    return AskResponse(
        query=query,
        answer=REFUSAL_TEXT,
        citations=[],
        cached=False,
        refused=True,
        message_key=REFUSAL_MESSAGE_KEY,
    )


def _response_from_validated(
    *,
    query: str,
    validated: ValidatedAnswer,
    cached: bool,
) -> AskResponse:
    refused = validated.answer_text.strip() == REFUSAL_TEXT
    return AskResponse(
        query=query,
        answer=validated.answer_text,
        citations=validated.citations,
        cached=cached,
        refused=refused,
        message_key=REFUSAL_MESSAGE_KEY if refused else None,
    )


def _response_from_cache(query: str, cached_payload: dict[str, Any]) -> AskResponse:
    answer = cached_payload.get("answer", {})
    if not isinstance(answer, dict):
        return _refusal_response(query)

    answer_text = answer.get("answer_text")
    if not isinstance(answer_text, str):
        return _refusal_response(query)

    raw_citations = answer.get("citations", [])
    citations: list[CitationRef] = []
    if isinstance(raw_citations, list):
        for item in raw_citations:
            if isinstance(item, dict):
                try:
                    citations.append(CitationRef.model_validate(item))
                except Exception:
                    logger.warning("Skipping malformed cached citation", exc_info=True)

    refused = bool(answer.get("refused", answer_text.strip() == REFUSAL_TEXT))
    message_key = answer.get("message_key")
    if refused and not isinstance(message_key, str):
        message_key = REFUSAL_MESSAGE_KEY

    return AskResponse(
        query=query,
        answer=answer_text,
        citations=citations,
        cached=True,
        refused=refused,
        message_key=message_key,
    )


def _response_from_workflow(query: str, result: WorkflowResult) -> AskResponse:
    return AskResponse(
        query=query,
        answer=result.answer_text,
        citations=result.citations,
        source="workflow",
        intent=result.intent.value,
        answer_key=result.answer_key,
        answer_params=result.answer_params,
        faq=result.faq,
        orders=result.orders,
        needs_location=result.needs_location,
        sign_in_required=result.sign_in_required,
    )


async def _fallback_response(
    *,
    client: Any,
    query: str,
    notice_key: str,
    signup_prompt_key: str | None = None,
    quota: AskQuota | None = None,
    workflow_retriever: WorkflowRetriever | None = None,
) -> AskResponse:
    """No-AI answer: ranked keyword search results + FAQ matches + a friendly note."""
    cards, faq = await fallback_results(client, query=query, retriever=workflow_retriever)
    return AskResponse(
        query=query,
        answer=FALLBACK_TEXT,
        citations=cards,
        source="fallback",
        notice_key=notice_key,
        signup_prompt_key=signup_prompt_key,
        faq=faq,
        quota=quota,
    )


def _notice_for_quota_error(exc: AppError) -> tuple[str, str | None]:
    details = exc.details or {}
    if exc.code == "ai_quota_kill_switch":
        return FALLBACK_AI_PAUSED_KEY, None
    i18n_key = details.get("i18n_key")
    signup = details.get("signup_prompt_key")
    return (
        i18n_key if isinstance(i18n_key, str) else "ai.quota.dailyExceeded",
        signup if isinstance(signup, str) else None,
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_ask(
    *,
    client: Any,
    query: str,
    user_id: str | None,
    guest_key: str,
    model_caller: Any | None = None,
    retriever: Any | None = None,
    client_ip: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    enable_workflow: bool = True,
    workflow_retriever: WorkflowRetriever | None = None,
) -> AskResponse:
    """Core ask pipeline — exposed for unit tests.

    Order: deterministic workflow (free) → answer cache (free) → quota reserve →
    RAG retrieval → LLM (primary, then cheap fallback model). Any quota/kill-switch
    stop or provider failure degrades to ranked search results + FAQ, never an error.
    """
    trimmed = query.strip()
    normalized = normalize_query(trimmed)

    def _status() -> AskQuota | None:
        return _optional_quota_status(
            client=client, user_id=user_id, guest_key=guest_key, client_ip=client_ip
        )

    # 1) Workflow-first: deterministic intents never touch the LLM or the quota.
    if enable_workflow:
        workflow: WorkflowResult | None = None
        try:
            workflow = await run_workflow(
                client,
                query=trimmed,
                user_id=user_id,
                lat=lat,
                lng=lng,
                retriever=workflow_retriever,
            )
        except Exception:  # noqa: BLE001 — a workflow bug must fall through, not break Ask
            logger.warning("Ask workflow intent failed; falling through", exc_info=True)
        if workflow is not None:
            response = _response_from_workflow(trimmed, workflow)
            response.quota = _status()
            _log_ask_analytics(
                client=client,
                query=trimmed,
                user_id=user_id,
                tokens=0,
                model="workflow",
                zero_result=not (workflow.citations or workflow.faq or workflow.orders),
            )
            return response

    # 2) Answer cache (query-keyed, user-agnostic).
    cached = cache_lookup(client, normalized_query=normalized)
    if cached is not None:
        response = _response_from_cache(trimmed, cached)
        response.quota = _status()
        _log_ask_analytics(
            client=client,
            query=trimmed,
            user_id=user_id,
            tokens=0,
            model="none",
            zero_result=response.refused,
        )
        return response

    # 3) Quota (daily per tier) + global monthly kill-switch.
    try:
        reservation = _optional_quota_check_and_reserve(
            client=client,
            user_id=user_id,
            guest_key=guest_key,
            question=normalized,
            client_ip=client_ip,
        )
    except AppError as exc:
        if exc.code not in _DEGRADE_TO_FALLBACK_CODES:
            raise
        notice_key, signup_key = _notice_for_quota_error(exc)
        quota = _quota_from_error_details(exc.details)
        if quota is None and exc.code == "ai_quota_kill_switch":
            quota = _status()
        _log_ask_analytics(
            client=client,
            query=trimmed,
            user_id=user_id,
            tokens=0,
            model="fallback",
            zero_result=False,
        )
        return await _fallback_response(
            client=client,
            query=trimmed,
            notice_key=notice_key,
            signup_prompt_key=signup_key,
            quota=quota,
            workflow_retriever=workflow_retriever,
        )

    quota_now = _quota_from_status(getattr(reservation, "status", None))

    # 4) Retrieval (FTS + trgm + vector RRF). A retrieval outage → fallback.
    extracted = extract_filters(trimmed)
    retrieve = retriever or top_k
    try:
        docs = await retrieve(client, query=extracted.search_query, filters=extracted.filters)
    except Exception:  # noqa: BLE001 — degrade, never break the page
        logger.warning("Ask retrieval failed; serving fallback", exc_info=True)
        _optional_quota_release(client=client, reservation=reservation)
        return await _fallback_response(
            client=client,
            query=trimmed,
            notice_key=FALLBACK_AI_UNAVAILABLE_KEY,
            quota=_status() or quota_now,
            workflow_retriever=workflow_retriever,
        )

    if not docs:
        refusal = _refusal_response(trimmed)
        cache_write(
            client,
            normalized_query=normalized,
            answer={
                "answer_text": refusal.answer,
                "citations": [],
                "refused": True,
                "message_key": REFUSAL_MESSAGE_KEY,
            },
            cited_ids=[],
        )
        _optional_quota_record_answer(
            client=client, user_id=user_id, guest_key=guest_key, tokens=0, model="none"
        )
        _log_ask_analytics(
            client=client,
            query=trimmed,
            user_id=user_id,
            tokens=0,
            model="none",
            zero_result=True,
        )
        refusal.quota = quota_now
        return refusal

    # 5) LLM (primary → cheap fallback model inside call_answer_model).
    prompt = build_prompt(query=trimmed, docs=docs)
    caller = model_caller or call_answer_model
    try:
        model_result = await caller(prompt)
    except Exception:  # noqa: BLE001 — provider down / out of credits / bad JSON
        logger.warning("Ask model call failed; serving fallback", exc_info=True)
        _optional_quota_release(client=client, reservation=reservation)
        _log_ask_analytics(
            client=client,
            query=trimmed,
            user_id=user_id,
            tokens=0,
            model="fallback",
            zero_result=False,
        )
        return await _fallback_response(
            client=client,
            query=trimmed,
            notice_key=FALLBACK_AI_UNAVAILABLE_KEY,
            quota=_status() or quota_now,
            workflow_retriever=workflow_retriever,
        )

    validated = validate_citations(
        answer_text=model_result.answer_text,
        cited_entity_ids=model_result.cited_entity_ids,
        retrieved_docs=docs,
    )

    cache_write(
        client,
        normalized_query=normalized,
        answer={
            "answer_text": validated.answer_text,
            "citations": [item.model_dump() for item in validated.citations],
            "refused": validated.answer_text.strip() == REFUSAL_TEXT,
            "message_key": REFUSAL_MESSAGE_KEY
            if validated.answer_text.strip() == REFUSAL_TEXT
            else None,
        },
        cited_ids=[item.entity_id for item in validated.citations],
    )
    _optional_quota_record_answer(
        client=client,
        user_id=user_id,
        guest_key=guest_key,
        tokens=model_result.total_tokens,
        model=model_result.model,
    )
    _log_ask_analytics(
        client=client,
        query=trimmed,
        user_id=user_id,
        tokens=model_result.total_tokens,
        model=model_result.model,
        zero_result=validated.answer_text.strip() == REFUSAL_TEXT,
    )

    response = _response_from_validated(query=trimmed, validated=validated, cached=False)
    response.quota = quota_now
    return response


@router.post("", response_model=AskResponse)
async def ask_vergeo(
    request: Request,
    body: AskRequest,
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> AskResponse:
    service_client = supabase.client
    _rate_limit_ask(request, service_client)

    current_user = await _optional_current_user(request)
    user_id = current_user.id if current_user is not None else None
    guest_key = _guest_key(request)

    try:
        return await run_ask(
            client=service_client,
            query=body.query,
            user_id=user_id,
            guest_key=guest_key,
            client_ip=get_client_ip(request),
            lat=body.lat,
            lng=body.lng,
        )
    except AppError:
        raise
    except Exception as exc:
        # Last-resort guard: even an unexpected failure returns a renderable fallback.
        logger.exception("Unexpected Ask Vergeo failure; serving fallback")
        try:
            return await _fallback_response(
                client=service_client,
                query=body.query.strip(),
                notice_key=FALLBACK_AI_UNAVAILABLE_KEY,
            )
        except Exception:  # noqa: BLE001
            raise AppError(
                code="ask_unavailable",
                message="Ask Vergeo is temporarily unavailable",
                http_status=503,
                details={"reason": exc.__class__.__name__},
            ) from exc


@router.get("/quota", response_model=AskQuota | None)
async def ask_quota(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> AskQuota | None:
    """Remaining Ask questions today for the caller (guest or signed-in). Read-only."""
    service_client = supabase.client
    _rate_limit(request, service_client, key_prefix="quota:", limit=QUOTA_RATE_LIMIT_PER_MINUTE)
    current_user = await _optional_current_user(request)
    return _optional_quota_status(
        client=service_client,
        user_id=current_user.id if current_user is not None else None,
        guest_key=_guest_key(request),
        client_ip=get_client_ip(request),
    )
