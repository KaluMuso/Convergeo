from __future__ import annotations

import importlib
import logging
from datetime import timedelta
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.ask.cache import cache_lookup, cache_write, normalize_query
from app.services.ask.citations import CitationRef, ValidatedAnswer, validate_citations
from app.services.ask.filters import extract_filters
from app.services.ask.prompt import build_prompt, call_answer_model
from app.services.ask.retrieve import top_k
from app.settings import get_settings
from fastapi import APIRouter, Depends, Request
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["ask"])

REFUSAL_TEXT = "I couldn't find that on Vergeo5."
REFUSAL_MESSAGE_KEY = "ai.answer.not_found"
RATE_LIMIT_MESSAGE_KEY = "ai.answer.rate_limited"

ASK_RATE_LIMIT_PER_MINUTE = 30


class AskRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)


class AskResponse(StrictModel):
    query: str
    answer: str
    citations: list[CitationRef]
    cached: bool = False
    refused: bool = False
    message_key: str | None = None


def _optional_quota_check_and_reserve(
    *, client: Any, user_id: str | None, guest_key: str, question: str
) -> None:
    try:
        quota = importlib.import_module("app.services.ask.quota")
    except ImportError:
        return

    check_and_reserve = getattr(quota, "check_and_reserve", None)
    if callable(check_and_reserve):
        check_and_reserve(
            client=client, user_id=user_id, guest_key=guest_key, question=question
        )


def _optional_quota_record_answer(
    *, client: Any, user_id: str | None, guest_key: str, tokens: int, model: str
) -> None:
    try:
        quota = importlib.import_module("app.services.ask.quota")
    except ImportError:
        return

    record_answer = getattr(quota, "record_answer", None)
    if callable(record_answer):
        record_answer(
            client=client,
            user_id=user_id,
            guest_key=guest_key,
            tokens=tokens,
            model=model,
        )


async def _optional_current_user(request: Request) -> CurrentUser | None:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return await get_current_user(request, get_settings())


def _rate_limit_ask(request: Request, service_client: Any) -> None:
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope="ask_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=ASK_RATE_LIMIT_PER_MINUTE,
        client=service_client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key=RATE_LIMIT_MESSAGE_KEY,
            message="Too many Ask Vergeo requests",
        )


def _guest_key(request: Request) -> str:
    device_id = request.headers.get("x-device-id", "").strip()
    if device_id:
        return f"device:{device_id}"
    return f"ip:{get_client_ip(request)}"


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


async def run_ask(
    *,
    client: Any,
    query: str,
    user_id: str | None,
    guest_key: str,
    model_caller: Any | None = None,
    retriever: Any | None = None,
) -> AskResponse:
    """Core ask pipeline — exposed for unit tests."""
    trimmed = query.strip()
    normalized = normalize_query(trimmed)

    cached = cache_lookup(client, normalized_query=normalized)
    if cached is not None:
        return _response_from_cache(trimmed, cached)

    _optional_quota_check_and_reserve(
        client=client, user_id=user_id, guest_key=guest_key, question=normalized
    )

    extracted = extract_filters(trimmed)
    retrieve = retriever or top_k
    docs = await retrieve(client, query=extracted.search_query, filters=extracted.filters)

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
        return refusal

    prompt = build_prompt(query=trimmed, docs=docs)
    caller = model_caller or call_answer_model
    model_result = await caller(prompt)

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

    return _response_from_validated(query=trimmed, validated=validated, cached=False)


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
        )
    except AppError:
        raise
    except RuntimeError as exc:
        logger.warning("Ask Vergeo pipeline failed", exc_info=True)
        raise AppError(
            code="ask_unavailable",
            message="Ask Vergeo is temporarily unavailable",
            http_status=503,
            details={"reason": exc.__class__.__name__},
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected Ask Vergeo failure")
        raise AppError(
            code="ask_unavailable",
            message="Ask Vergeo is temporarily unavailable",
            http_status=503,
            details={"reason": exc.__class__.__name__},
        ) from exc
