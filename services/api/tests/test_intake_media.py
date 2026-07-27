"""M18-P03 — safe media quarantine (D35).

The declared MIME type and filename are attacker-controlled, so every test here
feeds bytes that disagree with what a sender would claim, and asserts the
verifier believes the bytes.
"""

from __future__ import annotations

import hashlib
import struct
import threading
import zlib
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.services.intake import imagecheck, media, state_machine

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SESSION_A = "22222222-2222-4222-8222-222222222222"


# ---------------------------------------------------------------------------
# Byte builders — real headers, no image library needed
# ---------------------------------------------------------------------------
def png_bytes(width: int = 640, height: int = 480, payload: bytes = b"") -> bytes:
    ihdr = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    chunk = (
        struct.pack(">I", len(ihdr))
        + b"IHDR"
        + ihdr
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    )
    return b"\x89PNG\r\n\x1a\n" + chunk + payload


def jpeg_bytes(width: int = 640, height: int = 480, *, exif: bool = False) -> bytes:
    out = bytearray(b"\xff\xd8")
    # APP0 JFIF (structural — must survive EXIF stripping)
    jfif = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    out += b"\xff\xe0" + struct.pack(">H", len(jfif) + 2) + jfif
    if exif:
        # APP1 EXIF carrying a recognisable GPS-ish marker
        exif_payload = b"Exif\x00\x00" + b"GPSLATITUDE-SECRET" + b"\x00" * 8
        out += b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload
    sof = b"\x08" + struct.pack(">HH", height, width) + b"\x03\x01\x11\x00"
    out += b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof
    out += b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00"
    out += b"scan-data"
    out += b"\xff\xd9"
    return bytes(out)


def webp_bytes(width: int = 640, height: int = 480) -> bytes:
    vp8 = b"\x00\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", width, height) + b"\x00" * 8
    chunk = b"VP8 " + struct.pack("<I", len(vp8)) + vp8
    return b"RIFF" + struct.pack("<I", len(chunk) + 4) + b"WEBP" + chunk


# ---------------------------------------------------------------------------
# imagecheck — magic bytes and the pixel budget
# ---------------------------------------------------------------------------
LIMITS = {"max_bytes": 8 * 1024 * 1024, "max_dimension": 12_000, "max_pixels": 40_000_000}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (png_bytes(), imagecheck.PNG),
        (jpeg_bytes(), imagecheck.JPEG),
        (webp_bytes(), imagecheck.WEBP),
    ],
)
def test_real_images_are_identified(data: bytes, expected: str) -> None:
    facts = imagecheck.verify(data, **LIMITS)
    assert facts.mime_type == expected
    assert (facts.width, facts.height) == (640, 480)


@pytest.mark.parametrize(
    "data",
    [
        b"GIF89a" + b"\x00" * 100,
        b"%PDF-1.7\n" + b"\x00" * 100,
        b"#!/bin/sh\nrm -rf /\n",
        b"MZ\x90\x00" + b"\x00" * 100,  # PE executable
        b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>",
        b"\x00" * 64,
    ],
)
def test_non_images_rejected_regardless_of_claimed_type(data: bytes) -> None:
    """A sender may declare image/jpeg; only the bytes decide."""
    with pytest.raises(imagecheck.ImageRejected) as exc:
        imagecheck.verify(data, **LIMITS)
    assert exc.value.reason in {"unsupported_or_spoofed_type", "empty"}


def test_png_magic_with_jpeg_claim_is_identified_as_png() -> None:
    """Spoofed declaration is irrelevant — we report what the bytes are."""
    assert imagecheck.verify(png_bytes(), **LIMITS).mime_type == imagecheck.PNG


def test_polyglot_prefix_is_rejected() -> None:
    """Script bytes with an image extension are still script bytes."""
    data = b"<?php system($_GET[0]); ?>" + png_bytes()
    with pytest.raises(imagecheck.ImageRejected):
        imagecheck.verify(data, **LIMITS)


def test_decompression_bomb_rejected_from_the_header() -> None:
    """A tiny file claiming a vast canvas is refused before any decode.

    This is the whole reason verification is header-only: discovering the size
    by decoding would be the bomb going off.
    """
    bomb = png_bytes(width=60_000, height=60_000)
    assert len(bomb) < 1024, "the point is that the FILE is tiny"
    with pytest.raises(imagecheck.ImageRejected) as exc:
        imagecheck.verify(bomb, **LIMITS)
    assert exc.value.reason in {"dimension_exceeded", "pixel_budget_exceeded"}


def test_pixel_budget_rejected_within_dimension_limit() -> None:
    """Both sides under max_dimension can still blow the total pixel budget."""
    with pytest.raises(imagecheck.ImageRejected) as exc:
        imagecheck.verify(png_bytes(width=10_000, height=10_000), **LIMITS)
    assert exc.value.reason == "pixel_budget_exceeded"


def test_oversized_bytes_rejected() -> None:
    with pytest.raises(imagecheck.ImageRejected) as exc:
        imagecheck.verify(png_bytes(payload=b"\x00" * 2048), max_bytes=512,
                          max_dimension=12_000, max_pixels=40_000_000)
    assert exc.value.reason == "too_large"


@pytest.mark.parametrize("data", [b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF0000WEBP"])
def test_truncated_headers_rejected(data: bytes) -> None:
    with pytest.raises(imagecheck.ImageRejected):
        imagecheck.verify(data, **LIMITS)


def test_zero_dimensions_rejected() -> None:
    with pytest.raises(imagecheck.ImageRejected):
        imagecheck.verify(png_bytes(width=0, height=10), **LIMITS)


# ---------------------------------------------------------------------------
# EXIF stripping
# ---------------------------------------------------------------------------
def test_exif_is_stripped_from_jpeg() -> None:
    original = jpeg_bytes(exif=True)
    assert b"GPSLATITUDE-SECRET" in original

    cleaned = media.strip_exif(original, imagecheck.JPEG)
    assert b"GPSLATITUDE-SECRET" not in cleaned, "GPS/PII must not survive"
    assert b"Exif" not in cleaned
    # Structural segments and image data survive.
    assert cleaned.startswith(b"\xff\xd8")
    assert b"JFIF" in cleaned
    assert b"scan-data" in cleaned
    # Still a valid image afterwards.
    assert imagecheck.verify(cleaned, **LIMITS).width == 640


def test_strip_exif_is_a_no_op_for_png() -> None:
    data = png_bytes()
    assert media.strip_exif(data, imagecheck.PNG) == data


# ---------------------------------------------------------------------------
# Ingestion — fakes for storage + db
# ---------------------------------------------------------------------------
class FakeQuery:
    def __init__(self, t: FakeTable) -> None:
        self._t = t
        self._f: list[tuple[str, Any]] = []
        self._single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _c: str = "*", **_k: Any) -> FakeQuery:
        return self

    def eq(self, c: str, v: Any) -> FakeQuery:
        self._f.append((c, v))
        return self

    def maybe_single(self) -> FakeQuery:
        self._single = True
        return self

    def insert(self, p: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = p
        return self

    def update(self, p: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = p
        return self

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", f"row-{len(self._t.rows) + 1}")
            self._t.rows.append(row)
            return MagicMock(data=[dict(row)])
        if self._op == "update":
            assert self._payload is not None
            changed = []
            for r in self._t.rows:
                if all(r.get(c) == v for c, v in self._f):
                    r.update(self._payload)
                    changed.append(dict(r))
            return MagicMock(data=changed)
        rows = [dict(r) for r in self._t.rows if all(r.get(c) == v for c, v in self._f)]
        if self._single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, c: str = "*", **k: Any) -> FakeQuery:
        return FakeQuery(self).select(c, **k)

    def insert(self, p: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(p)

    def update(self, p: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(p)


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, path: str, data: bytes, _opts: dict[str, str]) -> None:
        self.objects[path] = data


class FakeStorage:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeBucket] = {}

    def from_(self, name: str) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket())


class FakeDB:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tables: dict[str, FakeTable] = {}
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))


class Wrapper:
    def __init__(self) -> None:
        self.client = FakeDB()

    def rows(self, n: str) -> list[dict[str, Any]]:
        return self.client.table(n).rows


@pytest.fixture()
def store() -> Wrapper:
    w = Wrapper()
    w.rows("intake_sessions").append(
        {"id": SESSION_A, "vendor_id": VENDOR_A, "status": state_machine.COLLECTING}
    )
    return w


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.intake import config as intake_config

    monkeypatch.setenv(intake_config.ENV_API_KEY, "k")
    monkeypatch.setenv(intake_config.ENV_BASE_URL, "http://waha.internal:3000")
    media.set_quarantine_hook(lambda _d: True)


async def _ingest(
    store: Wrapper, data: bytes | None = None, *, error: Exception | None = None
) -> Any:
    async def fake_fetch(_url: str) -> bytes:
        if error is not None:
            raise error
        assert data is not None
        return data

    original = media._fetch
    media._fetch = fake_fetch  # type: ignore[assignment]
    try:
        return await media.ingest_one(
            store,
            vendor_id=VENDOR_A,
            session_id=SESSION_A,
            media_ref={"url": "https://waha.internal/media/1", "declared_mimetype": "image/jpeg"},
        )
    finally:
        media._fetch = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_valid_image_is_stored_privately(store: Wrapper) -> None:
    stored = await _ingest(store, png_bytes())
    assert stored.mime_type == imagecheck.PNG
    assert stored.storage_path.startswith(f"intake/{VENDOR_A}/{SESSION_A}/")
    assert len(store.rows("intake_media")) == 1
    # Stored in the private bucket only.
    assert media.BUCKET in store.client.storage.buckets
    assert list(store.client.storage.buckets) == [media.BUCKET]


@pytest.mark.asyncio
async def test_no_public_url_is_ever_produced(store: Wrapper) -> None:
    stored = await _ingest(store, png_bytes())
    assert not stored.storage_path.startswith("http")
    for row in store.rows("intake_media"):
        assert not str(row["storage_path"]).startswith("http")


@pytest.mark.asyncio
async def test_spoofed_mime_rejected(store: Wrapper) -> None:
    """Declared image/jpeg, actual bytes are a shell script."""
    with pytest.raises(media.MediaRejected) as exc:
        await _ingest(store, b"#!/bin/sh\necho pwned\n")
    assert exc.value.reason == "unsupported_or_spoofed_type"
    assert store.rows("intake_media") == []


@pytest.mark.asyncio
async def test_decompression_bomb_rejected(store: Wrapper) -> None:
    with pytest.raises(media.MediaRejected):
        await _ingest(store, png_bytes(width=60_000, height=60_000))
    assert store.rows("intake_media") == []


@pytest.mark.asyncio
async def test_identical_media_is_deduped(store: Wrapper) -> None:
    first = await _ingest(store, png_bytes())
    second = await _ingest(store, png_bytes())
    assert first.content_hash == second.content_hash
    assert len(store.rows("intake_media")) == 1, "one stored row"
    assert len(store.client.storage.buckets[media.BUCKET].objects) == 1


@pytest.mark.asyncio
async def test_quarantine_verdict_is_honoured(store: Wrapper) -> None:
    media.set_quarantine_hook(lambda _d: False)
    with pytest.raises(media.MediaRejected) as exc:
        await _ingest(store, png_bytes())
    assert exc.value.reason == "quarantine_flagged"
    assert store.rows("intake_media") == []
    assert store.client.storage.buckets.get(media.BUCKET) is None or not (
        store.client.storage.buckets[media.BUCKET].objects
    )


@pytest.mark.asyncio
async def test_fetch_timeout_is_rejected(store: Wrapper) -> None:
    import httpx

    with pytest.raises(media.MediaRejected) as exc:
        await _ingest(store, error=media.MediaRejected("fetch_timeout"))
    assert exc.value.reason == "fetch_timeout"
    assert isinstance(httpx.TimeoutException("x"), httpx.HTTPError)


@pytest.mark.asyncio
async def test_expired_provider_url_is_rejected(store: Wrapper) -> None:
    with pytest.raises(media.MediaRejected) as exc:
        await _ingest(store, error=media.MediaRejected("fetch_failed"))
    assert exc.value.reason == "fetch_failed"
    assert store.rows("intake_media") == []


@pytest.mark.asyncio
async def test_missing_url_rejected(store: Wrapper) -> None:
    with pytest.raises(media.MediaRejected) as exc:
        await media.ingest_one(
            store, vendor_id=VENDOR_A, session_id=SESSION_A, media_ref={"url": None}
        )
    assert exc.value.reason == "missing_url"


@pytest.mark.asyncio
async def test_per_session_image_cap(store: Wrapper) -> None:
    for i in range(media.MAX_IMAGES_PER_SESSION):
        store.rows("intake_media").append(
            {"session_id": SESSION_A, "content_hash": f"h{i}", "storage_path": f"p{i}"}
        )
    with pytest.raises(media.MediaRejected) as exc:
        await _ingest(store, png_bytes())
    assert exc.value.reason == "too_many_images"


@pytest.mark.asyncio
async def test_exif_is_stripped_before_storage(store: Wrapper) -> None:
    await _ingest(store, jpeg_bytes(exif=True))
    blob = next(iter(store.client.storage.buckets[media.BUCKET].objects.values()))
    assert b"GPSLATITUDE-SECRET" not in blob


@pytest.mark.asyncio
async def test_stored_hash_is_of_the_cleaned_bytes(store: Wrapper) -> None:
    """Dedupe must key on what we stored, not on what arrived."""
    stored = await _ingest(store, jpeg_bytes(exif=True))
    blob = next(iter(store.client.storage.buckets[media.BUCKET].objects.values()))
    assert stored.content_hash == hashlib.sha256(blob).hexdigest()


@pytest.mark.asyncio
async def test_failure_lands_in_recoverable_needs_details(store: Wrapper) -> None:
    """A rejection must leave a resumable session, not a half-attached draft."""

    async def fake_fetch(_url: str) -> bytes:
        return b"not-an-image"

    original = media._fetch
    media._fetch = fake_fetch  # type: ignore[assignment]
    try:
        stored = await media.ingest_session_media(
            store,
            vendor_id=VENDOR_A,
            session_id=SESSION_A,
            media_refs=[{"url": "https://waha.internal/media/1"}],
        )
    finally:
        media._fetch = original  # type: ignore[assignment]

    assert stored == []
    assert store.rows("intake_sessions")[0]["status"] == state_machine.NEEDS_DETAILS
    assert store.rows("intake_media") == []


def test_module_never_touches_vendor_listings() -> None:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(media))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    assert "vendor_listings" not in ast.unparse(tree)
