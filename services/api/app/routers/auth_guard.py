from __future__ import annotations

from app.core.ratelimit import (
    check_and_increment_otp_quota,
    check_auth_endpoint_limit,
    get_client_ip,
)
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/auth/guard", tags=["auth-guard"])


class OtpQuotaRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        if digits.startswith("+"):
            return digits
        if digits.startswith("260"):
            return f"+{digits}"
        if digits.startswith("0"):
            return f"+260{digits[1:]}"
        return f"+{digits}"


class OtpQuotaResponse(BaseModel):
    allowed: bool = True
    message_key: str | None = None


async def require_otp_quota(
    phone: str,
    request: Request,
) -> None:
    """Reusable dependency for OTP send endpoints."""
    check_and_increment_otp_quota(phone=phone, ip=get_client_ip(request))


async def _auth_guard_request(request: Request) -> None:
    check_auth_endpoint_limit(request=request)


@router.post(
    "/otp-quota",
    response_model=OtpQuotaResponse,
    dependencies=[Depends(_auth_guard_request)],
)
async def consume_otp_quota(body: OtpQuotaRequest, request: Request) -> OtpQuotaResponse:
    """Check/increment OTP counters before dispatching an SMS OTP."""
    await require_otp_quota(body.phone, request)
    return OtpQuotaResponse(allowed=True)
