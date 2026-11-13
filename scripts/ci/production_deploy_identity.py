#!/usr/bin/env python3
"""Fail-closed identity checks for the manual production deployment workflow.

Identity validation is not release certification or permission to activate money.
Only public identifiers are returned; untrusted fingerprint values are never logged.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY = "KaluMuso/Convergeo"
PRODUCTION_REF = "refs/heads/master"
PRODUCTION_PROJECT = "dpadrlxukcjbewpqympu"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
MAX_FINGERPRINT_BYTES = 65_536


class ProductionIdentityError(ValueError):
    """A request or live fingerprint does not prove the exact production identity."""


def require_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or SHA_PATTERN.fullmatch(value) is None:
        raise ProductionIdentityError(f"{field} must be a full lowercase 40-character SHA")
    return value


def validate_request(
    *, repository: str, ref: str, source_sha: str, image_tag: str
) -> None:
    if repository != REPOSITORY or ref != PRODUCTION_REF:
        raise ProductionIdentityError("deployment requires this repository's master ref")
    require_sha(source_sha, "source_sha")
    require_sha(image_tag, "image_tag")
    if source_sha != image_tag:
        raise ProductionIdentityError("API image tag must equal the workflow checkout SHA")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProductionIdentityError("fingerprint contains duplicate JSON keys")
        result[key] = value
    return result


def read_fingerprint(path: Path) -> object:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_FINGERPRINT_BYTES + 1)
        if len(raw) > MAX_FINGERPRINT_BYTES:
            raise ProductionIdentityError("fingerprint exceeds the size limit")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProductionIdentityError("fingerprint is unreadable or invalid JSON") from exc


def validate_fingerprint(
    fingerprint: object, *, expected_sha: str, expected_project: str
) -> None:
    require_sha(expected_sha, "expected_sha")
    if expected_project != PRODUCTION_PROJECT:
        raise ProductionIdentityError("expected project is not the production project")
    if not isinstance(fingerprint, dict):
        raise ProductionIdentityError("fingerprint must be a JSON object")
    if fingerprint.get("env") != "production":
        raise ProductionIdentityError("fingerprint environment is not production")
    if fingerprint.get("supabase_project_ref") != expected_project:
        raise ProductionIdentityError("fingerprint Supabase project mismatch")
    for field in ("git_sha", "image_tag"):
        value = require_sha(fingerprint.get(field), field)
        if value != expected_sha:
            raise ProductionIdentityError(f"fingerprint {field} mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    request = subparsers.add_parser("request")
    for name in ("repository", "ref", "source-sha", "image-tag"):
        request.add_argument(f"--{name}", required=True)
    fingerprint = subparsers.add_parser("fingerprint")
    fingerprint.add_argument("--fingerprint-file", type=Path, required=True)
    fingerprint.add_argument("--expected-sha", required=True)
    fingerprint.add_argument("--expected-project", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "request":
            validate_request(
                repository=args.repository,
                ref=args.ref,
                source_sha=args.source_sha,
                image_tag=args.image_tag,
            )
        else:
            validate_fingerprint(
                read_fingerprint(args.fingerprint_file),
                expected_sha=args.expected_sha,
                expected_project=args.expected_project,
            )
    except ProductionIdentityError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print("Exact production identity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
