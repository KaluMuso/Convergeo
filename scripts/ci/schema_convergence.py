#!/usr/bin/env python3
"""Fail-closed schema-convergence manifest and sandbox rehearsal verifier.

This module deliberately does *not* connect to Supabase or apply migrations.
``rehearse-schema-convergence.sh`` is the small read-only adapter that obtains a
ledger through ``psql`` and passes it here.  Keeping the policy evaluation pure
makes it testable without credentials and prevents a CI job from accidentally
becoming a production migration path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PRODUCTION_PROJECT_REF = "dpadrlxukcjbewpqympu"
SANDBOX_PROJECT_REF = "iyasmrmbcrvlfxpzescb"
MIGRATION_FILE_RE = re.compile(r"^(?P<version>[0-9]+)_.+\.sql$")


class SchemaConvergenceError(ValueError):
    """Raised when a schema target, ledger, or launch profile is unsafe."""


@dataclass(frozen=True)
class Migration:
    """A repository migration identity, independent of its SQL contents."""

    version: str
    filename: str


def repository_migrations(migrations_dir: Path) -> list[Migration]:
    """Return deterministic migrations and refuse malformed or duplicate versions."""
    if not migrations_dir.is_dir():
        raise SchemaConvergenceError(f"migrations directory not found: {migrations_dir}")

    migrations: list[Migration] = []
    versions: set[str] = set()
    for path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_FILE_RE.fullmatch(path.name)
        if match is None:
            raise SchemaConvergenceError(f"malformed migration filename: {path.name}")
        version = match.group("version")
        if version in versions:
            raise SchemaConvergenceError(f"duplicate migration version: {version}")
        versions.add(version)
        migrations.append(Migration(version=version, filename=path.name))

    if not migrations:
        raise SchemaConvergenceError("repository has no migrations")
    return migrations


def parse_ledger(raw: str) -> list[str]:
    """Parse a one-version-per-line ledger produced by the read-only adapter."""
    versions: list[str] = []
    for line in raw.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if not re.fullmatch(r"[0-9]+", value):
            raise SchemaConvergenceError(f"malformed remote migration version: {value!r}")
        versions.append(value)
    return versions


def assert_sandbox_target(*, target_kind: str, target_project_ref: str) -> None:
    """Permit only the canonical sandbox target for automated verification."""
    normalized_kind = target_kind.strip().lower()
    normalized_ref = target_project_ref.strip().lower()
    if normalized_ref == PRODUCTION_PROJECT_REF:
        raise SchemaConvergenceError("production project ref is never a CI schema target")
    if normalized_kind != "sandbox":
        raise SchemaConvergenceError(
            "only target-kind=sandbox is supported; production change windows are manual"
        )
    if normalized_ref != SANDBOX_PROJECT_REF:
        raise SchemaConvergenceError(
            "sandbox target ref does not match the documented isolated project"
        )


def assert_contiguous_ledger(
    *,
    repository_versions: list[str],
    remote_versions: list[str],
) -> list[str]:
    """Require a non-empty remote ledger that is an ordered repository prefix.

    A remote ledger that is a prefix is allowed so this checker can be used both
    before and after a sandbox rehearsal.  Any gap, unknown version, duplicate,
    or reordering fails rather than being interpreted as a successful no-op.
    """
    if not remote_versions:
        raise SchemaConvergenceError(
            "remote ledger is empty; a connection/query result is required for a green gate"
        )
    if len(remote_versions) != len(set(remote_versions)):
        raise SchemaConvergenceError("remote ledger contains duplicate migration versions")
    if len(remote_versions) > len(repository_versions):
        raise SchemaConvergenceError("remote ledger is longer than repository history")

    expected = repository_versions[: len(remote_versions)]
    if remote_versions != expected:
        for index, (actual, wanted) in enumerate(zip(remote_versions, expected), start=1):
            if actual != wanted:
                raise SchemaConvergenceError(
                    "remote ledger is not an ordered repository prefix at position "
                    f"{index}: got {actual}, expected {wanted}"
                )
        raise SchemaConvergenceError("remote ledger is not an ordered repository prefix")

    return repository_versions[len(remote_versions) :]


def load_cohorts(path: Path) -> dict[str, Any]:
    """Load and minimally validate the checked-in non-secret release contract."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchemaConvergenceError(f"cohort manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaConvergenceError(f"invalid cohort manifest JSON: {exc.msg}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("cohorts"), list):
        raise SchemaConvergenceError("cohort manifest must contain a cohorts array")
    return value


def assert_v1_profile(manifest: dict[str, Any]) -> None:
    """Lock the release manifest to D33/D34's deliberately narrow launch scope."""
    profile = manifest.get("v1_release_profile")
    if not isinstance(profile, dict):
        raise SchemaConvergenceError("cohort manifest lacks v1_release_profile")

    expected = {
        "allowed_product_classes": ["A"],
        "allowed_conditions": ["new", "refurbished"],
        "allowed_sale_units": ["each"],
        "allowed_fulfilment_modes": ["stocked"],
        "allowed_admin_roles": ["admin"],
        "blocked_roles": ["superadmin", "moderator"],
    }
    for key, required in expected.items():
        if profile.get(key) != required:
            raise SchemaConvergenceError(
                f"v1 release profile {key} must be exactly {required!r}"
            )

    blocked = profile.get("blocked_migration_versions")
    if not isinstance(blocked, list) or not {"0085", "0087", "0091"}.issubset(blocked):
        raise SchemaConvergenceError(
            "v1 release profile must hold 0085, 0087, and 0091 activation paths"
        )


def cohort_by_id(manifest: dict[str, Any], cohort_id: str) -> dict[str, Any]:
    """Find a unique configured cohort."""
    matching = [item for item in manifest["cohorts"] if item.get("id") == cohort_id]
    if len(matching) != 1:
        raise SchemaConvergenceError(f"unknown or duplicate cohort id: {cohort_id}")
    cohort = matching[0]
    if not isinstance(cohort, dict):
        raise SchemaConvergenceError(f"cohort {cohort_id} is not an object")
    return cohort


def assert_rehearsal_cohort(
    *,
    manifest: dict[str, Any],
    cohort_id: str,
    repository_versions: list[str],
    remote_versions: list[str],
) -> list[str]:
    """Verify that a completed sandbox rehearsal stopped at its declared ledger tip."""
    cohort = cohort_by_id(manifest, cohort_id)
    if cohort.get("execution") != "sandbox-rehearsal":
        raise SchemaConvergenceError(f"cohort {cohort_id} is not executable in sandbox CI")
    through = cohort.get("through_version")
    if not isinstance(through, str) or through not in repository_versions:
        raise SchemaConvergenceError(f"cohort {cohort_id} has an invalid through_version")
    if not cohort.get("required_evidence"):
        raise SchemaConvergenceError(f"cohort {cohort_id} has no required evidence")

    pending = assert_contiguous_ledger(
        repository_versions=repository_versions,
        remote_versions=remote_versions,
    )
    if remote_versions[-1] != through:
        raise SchemaConvergenceError(
            f"cohort {cohort_id} requires remote ledger tip {through}, got {remote_versions[-1]}"
        )
    return pending


def manifest_digest(migrations: list[Migration], manifest: dict[str, Any]) -> str:
    """Hash identities plus policy contract for attestable, non-secret evidence."""
    payload = {
        "migrations": [{"version": m.version, "filename": m.filename} for m in migrations],
        "v1_release_profile": manifest.get("v1_release_profile"),
        "cohorts": manifest.get("cohorts"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrations-dir", type=Path, default=Path("supabase/migrations"))
    parser.add_argument(
        "--cohorts-file",
        type=Path,
        default=Path("scripts/ci/schema-convergence-cohorts.json"),
    )
    parser.add_argument("--print-manifest", action="store_true")
    parser.add_argument("--target-kind")
    parser.add_argument("--target-project-ref")
    parser.add_argument("--ledger-file", type=Path)
    parser.add_argument("--ledger-source")
    parser.add_argument("--cohort")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        migrations = repository_migrations(args.migrations_dir)
        manifest = load_cohorts(args.cohorts_file)
        assert_v1_profile(manifest)

        if args.print_manifest:
            print(
                json.dumps(
                    {
                        "migration_count": len(migrations),
                        "migration_tip": migrations[-1].version,
                        "manifest_sha256": manifest_digest(migrations, manifest),
                        "v1_release_profile": manifest["v1_release_profile"],
                        "cohorts": manifest["cohorts"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if not all((args.target_kind, args.target_project_ref, args.ledger_file, args.cohort)):
            raise SchemaConvergenceError(
                "target-kind, target-project-ref, ledger-file, and cohort are required"
            )
        if args.ledger_source != "live-query":
            raise SchemaConvergenceError(
                "ledger-source=live-query is required; fixtures cannot produce a green rehearsal"
            )
        assert_sandbox_target(
            target_kind=args.target_kind,
            target_project_ref=args.target_project_ref,
        )
        if not args.ledger_file.is_file():
            raise SchemaConvergenceError(f"remote ledger file not found: {args.ledger_file}")
        remote_versions = parse_ledger(args.ledger_file.read_text(encoding="utf-8"))
        pending = assert_rehearsal_cohort(
            manifest=manifest,
            cohort_id=args.cohort,
            repository_versions=[migration.version for migration in migrations],
            remote_versions=remote_versions,
        )
    except SchemaConvergenceError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(
        "schema convergence rehearsal OK: "
        f"cohort={args.cohort} ledger_tip={remote_versions[-1]} pending_after={len(pending)} "
        f"manifest_sha256={manifest_digest(migrations, manifest)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
