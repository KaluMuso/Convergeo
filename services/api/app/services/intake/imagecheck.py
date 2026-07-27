"""M18-P03 — header-only image verification (no decoding, no dependencies).

Everything here reads **headers only**. Nothing is ever decoded, which is what
makes the pixel-budget guard meaningful: a 100-megapixel "image" packed into
200 KB is rejected from its header, before any allocation proportional to its
claimed dimensions could happen. Decoding first to find out how big something is
would be the bomb going off.

Three formats are accepted — JPEG, PNG, WebP — identified by **magic bytes**.
The declared MIME type and filename from the provider are attacker-controlled
and are never consulted.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Final

JPEG: Final = "image/jpeg"
PNG: Final = "image/png"
WEBP: Final = "image/webp"

ACCEPTED_MIME_TYPES: Final[frozenset[str]] = frozenset({JPEG, PNG, WEBP})

_PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC: Final = b"\xff\xd8\xff"
_RIFF_MAGIC: Final = b"RIFF"
_WEBP_TAG: Final = b"WEBP"

# JPEG Start-Of-Frame markers carry the dimensions. DHT/DAC/RSTn/SOI/EOI are
# explicitly not SOF even though they sit in the same numeric range.
_SOF_MARKERS: Final[frozenset[int]] = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


class ImageRejected(ValueError):
    """The bytes are not an acceptable image. Carries a stable machine reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ImageFacts:
    """What we *verified*, as opposed to what the sender claimed."""

    mime_type: str
    width: int
    height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height


def sniff_mime(data: bytes) -> str | None:
    """Identify the format from magic bytes alone. None ⇒ not an accepted image."""
    if data.startswith(_PNG_MAGIC):
        return PNG
    if data.startswith(_JPEG_MAGIC):
        return JPEG
    if len(data) >= 12 and data.startswith(_RIFF_MAGIC) and data[8:12] == _WEBP_TAG:
        return WEBP
    return None


def _png_dimensions(data: bytes) -> tuple[int, int]:
    # IHDR must be the first chunk: 8 magic + 4 length + 4 type + 8 dimensions.
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ImageRejected("png_header_invalid")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    index = 2  # skip SOI
    length = len(data)
    while index + 3 < length:
        if data[index] != 0xFF:
            # Not aligned on a marker — refuse rather than resynchronise, since
            # a permissive parser is exactly where polyglots live.
            raise ImageRejected("jpeg_header_invalid")
        marker = data[index + 1]
        index += 2
        # Standalone markers carry no payload.
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 1 >= length:
            break
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        if segment_length < 2:
            raise ImageRejected("jpeg_header_invalid")
        if marker in _SOF_MARKERS:
            if index + 7 > length:
                break
            height, width = struct.unpack(">HH", data[index + 3 : index + 7])
            return int(width), int(height)
        index += segment_length
    raise ImageRejected("jpeg_dimensions_not_found")


def _webp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 30:
        raise ImageRejected("webp_header_invalid")
    chunk = data[12:16]
    if chunk == b"VP8 ":
        # Lossy: 3-byte frame tag, 3-byte start code, then 14-bit dimensions.
        if len(data) < 30 or data[23:26] != b"\x9d\x01\x2a":
            raise ImageRejected("webp_header_invalid")
        width, height = struct.unpack("<HH", data[26:30])
        return int(width & 0x3FFF), int(height & 0x3FFF)
    if chunk == b"VP8L":
        if len(data) < 25 or data[20] != 0x2F:
            raise ImageRejected("webp_header_invalid")
        bits = struct.unpack("<I", data[21:25])[0]
        return int((bits & 0x3FFF) + 1), int(((bits >> 14) & 0x3FFF) + 1)
    if chunk == b"VP8X":
        if len(data) < 30:
            raise ImageRejected("webp_header_invalid")
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    raise ImageRejected("webp_header_invalid")


def verify(
    data: bytes,
    *,
    max_bytes: int,
    max_dimension: int,
    max_pixels: int,
) -> ImageFacts:
    """Verify bytes are a real, sanely-sized image. Raises :class:`ImageRejected`.

    Order matters: size, then magic bytes, then header-derived dimensions. The
    dimension check happens without decoding, so an image claiming a vast canvas
    is refused before it can cost anything.
    """
    if not data:
        raise ImageRejected("empty")
    if len(data) > max_bytes:
        raise ImageRejected("too_large")

    mime = sniff_mime(data)
    if mime is None:
        raise ImageRejected("unsupported_or_spoofed_type")

    if mime == PNG:
        width, height = _png_dimensions(data)
    elif mime == JPEG:
        width, height = _jpeg_dimensions(data)
    else:
        width, height = _webp_dimensions(data)

    if width <= 0 or height <= 0:
        raise ImageRejected("invalid_dimensions")
    if width > max_dimension or height > max_dimension:
        raise ImageRejected("dimension_exceeded")
    if width * height > max_pixels:
        # The decompression-bomb guard: a small file may still claim a canvas
        # far too large to ever process.
        raise ImageRejected("pixel_budget_exceeded")

    return ImageFacts(mime_type=mime, width=width, height=height)
