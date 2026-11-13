#!/usr/bin/env python3
"""Select and validate a Vercel Preview environment variable for a Git branch.

Extracted from vercel-staging-preview-prove.sh so the branch-override
selection and ciphertext-safety logic is independently unit-testable
(previously an inline bash heredoc with no test coverage).

Vercel allows two coexisting rows for the same key/Preview target: a generic
Preview value (no ``gitBranch``) and a Preview value scoped to a specific
``gitBranch``. This module selects deterministically between them — the
branch-scoped row always wins over a generic one — and fails closed when the
staging contract requires a branch override that is not present, rather than
silently falling back to a generic Preview value.

It also refuses to interpret a still-encrypted Vercel env row (``decrypted``
is not ``true`` for an encrypted/secret/sensitive variable — the shape
returned when ``decrypt=true`` is omitted from the API request) as a
hostname, since Vercel returns ciphertext, not the plaintext value, in that
case.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FORBIDDEN_HOST_SUBSTRINGS = ("api.vergeo5.com", "localhost")
ENCRYPTED_TYPES = {"encrypted", "secret", "sensitive"}


@dataclass(frozen=True)
class SelectionResult:
    """Outcome of selecting/validating one Preview env row.

    ``verdict`` is one of: verified, missing, missing_branch_override,
    forbidden, ciphertext, host_mismatch. ``host`` is populated only for
    verified/host_mismatch and is never printed by the CLI — callers that
    need it (e.g. tests) use it directly, but no code path here logs it.
    """

    verdict: str
    host: str | None = None


def _targets(row: dict[str, Any]) -> set[str]:
    target = row.get("target") or []
    if isinstance(target, str):
        target = [target]
    return {str(t).lower() for t in target}


def _row_branch(row: dict[str, Any]) -> str:
    return row.get("gitBranch") or row.get("branch") or ""


def _is_ciphertext(row: dict[str, Any]) -> bool:
    row_type = row.get("type")
    if row_type in ENCRYPTED_TYPES and row.get("decrypted") is not True:
        return True
    value = row.get("value") or ""
    # Defense in depth: even if type/decrypted metadata is ever missing,
    # never treat a long, dot-free blob as a hostname.
    if len(value) > 40 and "." not in value and "://" not in value:
        return True
    return False


def _extract_host(value: str) -> str:
    return value.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()


def select_env_row(
    rows: list[dict[str, Any]],
    key: str,
    git_branch: str,
    require_branch_override: bool = True,
) -> SelectionResult:
    """Deterministically pick the Preview row for ``key`` on ``git_branch``.

    A row with ``gitBranch == git_branch`` always takes precedence over a
    generic Preview row (no gitBranch) for the same key — regardless of
    result ordering from the API. When ``require_branch_override`` is True
    (the staging contract), a generic-only match is not an acceptable
    substitute for a missing branch override: the caller must fail closed.
    """
    branch_rows: list[dict[str, Any]] = []
    generic_rows: list[dict[str, Any]] = []

    for row in rows:
        if row.get("key") != key:
            continue
        if "preview" not in _targets(row):
            continue
        row_branch = _row_branch(row)
        if row_branch == git_branch:
            branch_rows.append(row)
        elif not row_branch:
            generic_rows.append(row)
        # Rows scoped to a different, non-matching git branch are never candidates.

    if branch_rows:
        chosen = sorted(branch_rows, key=lambda r: r.get("updatedAt") or 0)[-1]
        return _classify(chosen)

    if generic_rows:
        if require_branch_override:
            return SelectionResult("missing_branch_override")
        chosen = sorted(generic_rows, key=lambda r: r.get("updatedAt") or 0)[-1]
        return _classify(chosen)

    return SelectionResult("missing")


def _classify(row: dict[str, Any]) -> SelectionResult:
    if _is_ciphertext(row):
        return SelectionResult("ciphertext")
    value = row.get("value") or ""
    if not value:
        return SelectionResult("missing")
    if any(bad in value.lower() for bad in FORBIDDEN_HOST_SUBSTRINGS):
        return SelectionResult("forbidden")
    return SelectionResult("verified", host=_extract_host(value))


def verify(
    rows: list[dict[str, Any]],
    key: str,
    git_branch: str,
    expected_host: str,
    require_branch_override: bool = True,
) -> SelectionResult:
    result = select_env_row(rows, key, git_branch, require_branch_override)
    if result.verdict != "verified":
        return result
    assert result.host is not None
    if result.host != expected_host.lower():
        return SelectionResult("host_mismatch", host=result.host)
    return result


def _rows_from_doc(doc: Any) -> list[dict[str, Any]] | None:
    rows = doc if isinstance(doc, list) else doc.get("envs", doc.get("environmentVariables", []))
    if not isinstance(rows, list):
        return None
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select/validate a Vercel Preview env var for a Git branch"
    )
    parser.add_argument("--key", required=True, help="Environment variable name")
    parser.add_argument("--git-branch", required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--env-json-file", type=Path, required=True)
    parser.add_argument(
        "--allow-generic-fallback",
        action="store_true",
        help="Accept a generic Preview value when no branch-specific override exists",
    )
    args = parser.parse_args(argv)

    doc = json.loads(args.env_json_file.read_text(encoding="utf-8"))
    rows = _rows_from_doc(doc)
    if rows is None:
        print("missing")
        return 0

    result = verify(
        rows,
        args.key,
        args.git_branch,
        args.expected_host,
        require_branch_override=not args.allow_generic_fallback,
    )
    # Only the verdict word is ever printed — never the row value, decrypted
    # or not, and never the expected/actual host content.
    print(result.verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
