from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import unquote

CLOUDINARY_URL_PATTERN = re.compile(
    r"^cloudinary://(?P<api_key>[^:]+):(?P<api_secret>[^@]+)@(?P<cloud_name>.+)$"
)

DEFAULT_ALLOWED_FORMATS = "jpg,png,webp,avif"


class CloudinaryUrlError(ValueError):
    """Raised when CLOUDINARY_URL cannot be parsed."""


def parse_cloudinary_url(url: str) -> tuple[str, str, str]:
    """Parse cloudinary://<api_key>:<api_secret>@<cloud_name> into credentials."""
    match = CLOUDINARY_URL_PATTERN.match(url.strip())
    if not match:
        raise CloudinaryUrlError("CLOUDINARY_URL must match cloudinary://<api_key>:<api_secret>@<cloud_name>")

    cloud_name = unquote(match.group("cloud_name"))
    api_key = unquote(match.group("api_key"))
    api_secret = unquote(match.group("api_secret"))
    if not cloud_name or not api_key or not api_secret:
        raise CloudinaryUrlError("CLOUDINARY_URL is missing cloud_name, api_key, or api_secret")

    return cloud_name, api_key, api_secret


def sign_upload_parameters(params: dict[str, Any], api_secret: str) -> str:
    """Compute Cloudinary's SHA-1 upload signature for the given parameters."""
    serialized = [
        f"{key}={value}"
        for key, value in params.items()
        if value is not None and value != ""
    ]
    to_sign = "&".join(sorted(serialized)) + api_secret
    return hashlib.sha1(to_sign.encode("utf-8")).hexdigest()


def build_signed_params(
    *,
    folder: str,
    public_id: str | None,
    timestamp: int,
    api_secret: str,
    allowed_formats: str = DEFAULT_ALLOWED_FORMATS,
    max_bytes: int,
) -> dict[str, str | int]:
    """Build signed Cloudinary upload parameters without exposing api_secret."""
    params_to_sign: dict[str, Any] = {
        "allowed_formats": allowed_formats,
        "folder": folder,
        "max_file_size": max_bytes,
        "timestamp": timestamp,
    }
    if public_id:
        params_to_sign["public_id"] = public_id

    signature = sign_upload_parameters(params_to_sign, api_secret)
    signed: dict[str, str | int] = {
        "allowed_formats": allowed_formats,
        "folder": folder,
        "max_file_size": max_bytes,
        "signature": signature,
        "timestamp": timestamp,
    }
    if public_id:
        signed["public_id"] = public_id

    return signed
