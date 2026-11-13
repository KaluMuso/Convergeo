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


# ---------------------------------------------------------------------------
# M17-P02 — video (clip) preset
# ---------------------------------------------------------------------------
# Deliberately a SEPARATE set of constants and a separate builder rather than
# widening the image path. A video preset that leaked into `listing` signing
# would raise the image size cap eightfold and admit video formats to a surface
# that has never accepted them; keeping the two apart makes that impossible by
# construction rather than by review.
CLIP_ALLOWED_FORMATS = "mp4,mov,webm"

#: D-V3: 80 MB upload ceiling.
MAX_CLIP_BYTES = 83_886_080

#: D-V3: <=60s. Cloudinary rejects longer input at upload, before we pay to
#: transcode it — cheaper than accepting the bytes and rejecting at callback.
MAX_CLIP_DURATION_S = 60

#: D-V4: progressive H.264 MP4 at two ceilings (480p cellular / 720p Wi-Fi) plus
#: a WebP poster. Deliberately NOT HLS: hls.js is ~70 KB gz and would consume
#: half a customer route budget on its own, and native <video> plays progressive
#: MP4 everywhere with range-request seeking.
CLIP_EAGER_TRANSFORMATIONS = (
    "c_limit,h_854,w_480,vc_h264,f_mp4/"
    "c_limit,h_1280,w_720,vc_h264,f_mp4/"
    "so_0,w_480,c_limit,f_webp,q_auto"
)


def build_signed_clip_params(
    *,
    folder: str,
    public_id: str | None,
    timestamp: int,
    api_secret: str,
    notification_url: str | None = None,
    eager: str = CLIP_EAGER_TRANSFORMATIONS,
    allowed_formats: str = CLIP_ALLOWED_FORMATS,
    max_bytes: int = MAX_CLIP_BYTES,
    max_duration_s: int = MAX_CLIP_DURATION_S,
) -> dict[str, str | int]:
    """Build signed Cloudinary params for a vendor clip upload.

    Every parameter that goes into the signature is also returned to the client.
    That symmetry is the whole point: a signed-but-unreturned parameter is the
    documented cause of Cloudinary's ``#416 Invalid Signature`` (see the note on
    ``SignUploadResponse`` in ``routers/media.py``), and adding eager/notification
    parameters here is exactly where that bug would reappear.

    ``api_secret`` is used to compute the signature and never returned.
    """
    params_to_sign: dict[str, Any] = {
        "allowed_formats": allowed_formats,
        "eager": eager,
        # Async so no request — and no vendor — waits on transcoding.
        "eager_async": "true",
        "folder": folder,
        "max_file_size": max_bytes,
        "timestamp": timestamp,
    }
    if max_duration_s:
        params_to_sign["duration"] = max_duration_s
    if notification_url:
        params_to_sign["eager_notification_url"] = notification_url
        params_to_sign["notification_url"] = notification_url
    if public_id:
        params_to_sign["public_id"] = public_id

    signature = sign_upload_parameters(params_to_sign, api_secret)

    signed: dict[str, str | int] = {
        key: value for key, value in params_to_sign.items() if value is not None
    }
    signed["signature"] = signature
    return signed
