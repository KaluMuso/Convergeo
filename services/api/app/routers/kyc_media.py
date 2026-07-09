"""KYC document signed-upload endpoint (M12-P02b).

Issues a short-lived Supabase Storage signed upload URL for a vendor's KYC
documents in the private ``kyc-docs`` bucket. The private bucket + RLS-default-
deny on ``storage.objects`` means only the service-role backend can touch it;
this endpoint pins the upload path to ``kyc/{vendor_id}/…`` so a vendor cannot
write into another vendor's folder.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal, Protocol

from app.deps import get_supabase_client
from app.errors import AppError
from app.media.authz import VendorScope, require_vendor_scope
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/media", tags=["media"])


class _StorageServiceClient(Protocol):
    """Structural type for the service-role client's storage surface.

    Declared locally (not imported from ``app.supabase_client``) so this module
    stays outside the service-role import allowlist — the client is provided by
    the ``get_supabase_client`` dependency, which owns that import.
    """

    @property
    def client(self) -> Any: ...

KYC_DOCS_BUCKET = "kyc-docs"
MAX_KYC_DOC_BYTES = 10_485_760  # 10 MiB — matches the config.toml bucket limit.


class KycDocSignRequest(BaseModel):
    resource_kind: Literal["kyc_doc"] = "kyc_doc"
    doc_type: Literal["nrc", "selfie"]
    file_size_bytes: int = Field(ge=1)


class KycDocSignResponse(BaseModel):
    bucket: str
    path: str
    token: str
    signed_url: str


def _extract_signed_upload(result: Any, *, path: str) -> tuple[str, str]:
    """Pull (signed_url, token) from storage3's create_signed_upload_url result.

    storage3 has returned both camelCase and snake_case across versions, and
    either a dict or an object — handle all defensively.
    """

    def _get(key_snake: str, key_camel: str) -> str | None:
        if isinstance(result, dict):
            value = result.get(key_snake, result.get(key_camel))
        else:
            value = getattr(result, key_snake, None) or getattr(result, key_camel, None)
        return value if isinstance(value, str) and value else None

    signed_url = _get("signed_url", "signedUrl")
    token = _get("token", "token")
    if not signed_url or not token:
        raise AppError(
            code="storage_error",
            message="Storage did not return a usable signed upload URL",
            http_status=502,
            details={"path": path},
        )
    return signed_url, token


@router.post("/kyc-doc/sign", response_model=KycDocSignResponse)
async def sign_kyc_doc_upload(
    body: KycDocSignRequest,
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    service_client: Annotated[_StorageServiceClient, Depends(get_supabase_client)],
) -> KycDocSignResponse:
    if body.file_size_bytes > MAX_KYC_DOC_BYTES:
        raise AppError(
            code="file_too_large",
            message="KYC document exceeds the maximum allowed upload size",
            http_status=400,
            details={"file_size_bytes": body.file_size_bytes, "max_bytes": MAX_KYC_DOC_BYTES},
        )

    # Path pinned to the caller's vendor folder — a vendor cannot sign into
    # another vendor's KYC folder.
    path = f"kyc/{scope.vendor_id}/{body.doc_type}-{int(time.time())}"

    try:
        result = service_client.client.storage.from_(KYC_DOCS_BUCKET).create_signed_upload_url(path)
    except Exception as exc:  # noqa: BLE001 — surface any storage failure as an envelope error
        raise AppError(
            code="storage_error",
            message="Could not create a signed upload URL",
            http_status=502,
            details={"path": path},
        ) from exc

    signed_url, token = _extract_signed_upload(result, path=path)
    return KycDocSignResponse(
        bucket=KYC_DOCS_BUCKET,
        path=path,
        token=token,
        signed_url=signed_url,
    )
