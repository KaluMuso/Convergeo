"""Validate private KYC document evidence before submission or approval."""

from __future__ import annotations

import re
from typing import Any, Protocol

from app.errors import AppError
from storage3.exceptions import StorageApiError

KYC_DOCS_BUCKET = "kyc-docs"
_SIGNED_DOC_NAME = re.compile(r"(nrc|selfie)-[0-9]+\Z")
_T1_REQUIRED_TYPES = frozenset({"nrc", "selfie"})
MAX_KYC_DOCUMENT_PATHS = 8
MAX_KYC_DOCUMENT_PATH_LENGTH = 120


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def validate_kyc_document_evidence(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    tier: int,
    paths: list[str],
) -> None:
    """Require owned signer-shaped keys and objects in the private bucket.

    The current signer issues NRC and selfie keys. T1 requires both; no higher-
    tier document naming contract is encoded by this signer yet.
    """
    validate_kyc_document_paths(vendor_id=vendor_id, tier=tier, paths=paths)

    try:
        bucket = service_client.client.storage.from_(KYC_DOCS_BUCKET)
    except Exception as exc:
        raise AppError(
            code="kyc_storage_unavailable",
            message="KYC document storage could not be checked",
            http_status=503,
        ) from exc

    for path in paths:
        try:
            exists = bucket.exists(path)
        except StorageApiError as exc:
            if str(exc.status) == "404":
                exists = False
            else:
                raise AppError(
                    code="kyc_storage_unavailable",
                    message="KYC document storage could not be checked",
                    http_status=503,
                ) from exc
        except Exception as exc:
            raise AppError(
                code="kyc_storage_unavailable",
                message="KYC document storage could not be checked",
                http_status=503,
            ) from exc
        if not exists:
            raise AppError(
                code="kyc_document_missing",
                message="A required KYC document is not stored",
                http_status=422,
            )


def validate_kyc_document_paths(
    *, vendor_id: str, tier: int, paths: list[str], require_complete: bool = True
) -> None:
    """Check key shape and ownership; optionally require submission completeness."""
    if (
        len(paths) > MAX_KYC_DOCUMENT_PATHS
        or (require_complete and not paths)
        or len(paths) != len(set(paths))
    ):
        raise AppError(
            code="kyc_documents_invalid",
            message="KYC document paths must be bounded, present and distinct",
            http_status=422,
        )

    prefix = f"kyc/{vendor_id}/"
    types: set[str] = set()
    for path in paths:
        if len(path) > MAX_KYC_DOCUMENT_PATH_LENGTH:
            raise AppError(
                code="kyc_documents_invalid",
                message="KYC document path is too long",
                http_status=422,
            )
        if not path.startswith(prefix):
            raise AppError(
                code="kyc_documents_invalid",
                message="KYC document path is outside the vendor folder",
                http_status=422,
            )
        match = _SIGNED_DOC_NAME.fullmatch(path[len(prefix) :])
        if match is None:
            raise AppError(
                code="kyc_documents_invalid",
                message="KYC document path does not match the KYC signer format",
                http_status=422,
            )
        types.add(match.group(1))

    if require_complete and tier == 1 and not _T1_REQUIRED_TYPES.issubset(types):
        raise AppError(
            code="kyc_documents_required",
            message="Tier 1 requires NRC and selfie documents",
            http_status=422,
        )
