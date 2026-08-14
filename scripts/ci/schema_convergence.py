#!/usr/bin/env python3
"""Fail-closed schema-convergence manifest and sandbox rehearsal verifier.

This module deliberately does *not* connect to Supabase or apply migrations.
``rehearse-schema-convergence.sh`` and ``preflight-staging-schema-convergence.sh``
are read-only adapters that obtain a ledger through ``psql`` and pass it here.
Keeping the policy evaluation pure makes it testable without credentials and
prevents a CI job from accidentally becoming a production migration path.
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
STAGING_LEDGER_REPAIR_REQUIRED = "STAGING_LEDGER_REPAIR_REQUIRED"


class SchemaConvergenceError(ValueError):
    """Raised when a schema target, ledger, or launch profile is unsafe."""


@dataclass(frozen=True)
class Migration:
    """A repository migration identity, independent of its SQL contents."""

    version: str
    filename: str


@dataclass(frozen=True)
class ConvergencePlan:
    """Deterministic classification of repository vs remote migration ledgers."""

    canonical_already_applied: list[str]
    equivalent_remote_aliases: list[dict[str, str]]
    superseded_rehearsal_rows: list[dict[str, str]]
    truly_pending_repository_migrations: list[str]
    unresolved_remote_versions: list[str]
    ledger_repair_required: bool
    manifest_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_already_applied": self.canonical_already_applied,
            "equivalent_remote_aliases": self.equivalent_remote_aliases,
            "superseded_rehearsal_rows": self.superseded_rehearsal_rows,
            "truly_pending_repository_migrations": self.truly_pending_repository_migrations,
            "unresolved_remote_versions": self.unresolved_remote_versions,
            "ledger_repair_required": self.ledger_repair_required,
            "manifest_sha256": self.manifest_sha256,
        }


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


def load_equivalence_manifest(path: Path, *, expected_source_sha: str | None = None) -> dict[str, Any]:
    """Load the staging drift equivalence manifest and validate its binding."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchemaConvergenceError(f"equivalence manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaConvergenceError(f"invalid equivalence manifest JSON: {exc.msg}") from exc

    if not isinstance(value, dict):
        raise SchemaConvergenceError("equivalence manifest must be a JSON object")
    if value.get("sandbox_project_ref") != SANDBOX_PROJECT_REF:
        raise SchemaConvergenceError("equivalence manifest sandbox_project_ref mismatch")
    verified = value.get("verified_source_sha")
    if not isinstance(verified, str) or not verified:
        raise SchemaConvergenceError("equivalence manifest lacks verified_source_sha")
    if expected_source_sha and verified != expected_source_sha:
        raise SchemaConvergenceError(
            "equivalence manifest verified_source_sha does not match repository HEAD"
        )
    for key in ("exact_aliases", "superseded_rehearsals"):
        if not isinstance(value.get(key), list):
            raise SchemaConvergenceError(f"equivalence manifest must contain {key} array")
    return value


def equivalence_manifest_digest(manifest: dict[str, Any]) -> str:
    """Hash the equivalence manifest for attestation."""
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_alias_hashes(
    *,
    migrations_dir: Path,
    manifest: dict[str, Any],
) -> None:
    """Refuse stale alias evidence when canonical migration files changed."""
    for alias in manifest["exact_aliases"]:
        if alias.get("equivalence") != "exact_sql":
            raise SchemaConvergenceError(
                f"unsupported alias equivalence for {alias.get('remote_version')}"
            )
        canonical_version = alias.get("canonical_version")
        canonical_filename = alias.get("canonical_filename")
        if not isinstance(canonical_version, str) or not isinstance(canonical_filename, str):
            raise SchemaConvergenceError("alias entry missing canonical version metadata")
        path = migrations_dir / canonical_filename
        if not path.is_file():
            raise SchemaConvergenceError(f"canonical migration missing: {canonical_filename}")
        actual = normalize_migration_sql(path.read_text(encoding="utf-8"))
        actual_sha = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        expected_sha = alias.get("canonical_normalized_sha256")
        if actual_sha != expected_sha:
            raise SchemaConvergenceError(
                f"canonical migration hash mismatch for {canonical_version}; "
                "equivalence manifest is stale"
            )
        remote_sha = alias.get("remote_normalized_sha256")
        if actual_sha != remote_sha:
            raise SchemaConvergenceError(
                f"alias remote hash mismatch for {alias.get('remote_version')}; "
                "remote SQL is not exact-equivalent to canonical file"
            )


def normalize_migration_sql(text: str) -> str:
    """Normalize semantically irrelevant whitespace for reproducible SQL hashes."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def classify_staging_ledger(
    *,
    repository_versions: list[str],
    remote_versions: list[str],
    manifest: dict[str, Any],
) -> ConvergencePlan:
    """Classify drift using explicit alias and superseded-rehearsal evidence only."""
    if not remote_versions:
        raise SchemaConvergenceError("remote ledger is empty")
    if len(remote_versions) != len(set(remote_versions)):
        raise SchemaConvergenceError("remote ledger contains duplicate migration versions")

    alias_by_remote = {
        item["remote_version"]: item["canonical_version"]
        for item in manifest["exact_aliases"]
        if isinstance(item, dict) and "remote_version" in item and "canonical_version" in item
    }
    if len(alias_by_remote) != len(manifest["exact_aliases"]):
        raise SchemaConvergenceError("equivalence manifest contains duplicate remote aliases")

    superseded_remote = {
        item["remote_version"]: item
        for item in manifest["superseded_rehearsals"]
        if isinstance(item, dict) and "remote_version" in item
    }
    if len(superseded_remote) != len(manifest["superseded_rehearsals"]):
        raise SchemaConvergenceError("equivalence manifest contains duplicate rehearsal rows")

    overlap = set(alias_by_remote) & set(superseded_remote)
    if overlap:
        raise SchemaConvergenceError(
            "remote version cannot be both alias and superseded rehearsal: "
            + ", ".join(sorted(overlap))
        )

    repo_set = set(repository_versions)
    unresolved: list[str] = []
    aliases: list[dict[str, str]] = []
    superseded: list[dict[str, str]] = []
    canonical_applied: list[str] = []

    for remote_version in remote_versions:
        if remote_version in alias_by_remote:
            canonical_version = alias_by_remote[remote_version]
            if canonical_version not in repo_set:
                raise SchemaConvergenceError(
                    f"alias canonical version absent from repository: {canonical_version}"
                )
            aliases.append(
                {
                    "remote_version": remote_version,
                    "canonical_version": canonical_version,
                }
            )
            canonical_applied.append(canonical_version)
            continue
        if remote_version in superseded_remote:
            entry = superseded_remote[remote_version]
            superseded.append(
                {
                    "remote_version": remote_version,
                    "remote_name": str(entry.get("remote_name", "")),
                    "classification": str(entry.get("classification", "")),
                }
            )
            continue
        if remote_version not in repo_set:
            unresolved.append(remote_version)
            continue
        canonical_applied.append(remote_version)

    if unresolved:
        return ConvergencePlan(
            canonical_already_applied=canonical_applied,
            equivalent_remote_aliases=aliases,
            superseded_rehearsal_rows=superseded,
            truly_pending_repository_migrations=[],
            unresolved_remote_versions=unresolved,
            ledger_repair_required=True,
            manifest_sha256=equivalence_manifest_digest(manifest),
        )

    canonical_applied_set = set(canonical_applied)
    canonical_applied_sorted = sorted(
        canonical_applied_set,
        key=lambda version: repository_versions.index(version),
    )

    pending = [version for version in repository_versions if version not in canonical_applied_set]
    unknown_remote = [version for version in remote_versions if version not in repo_set]
    ledger_repair_required = bool(aliases or superseded or unknown_remote)

    return ConvergencePlan(
        canonical_already_applied=canonical_applied_sorted,
        equivalent_remote_aliases=aliases,
        superseded_rehearsal_rows=superseded,
        truly_pending_repository_migrations=pending,
        unresolved_remote_versions=[],
        ledger_repair_required=ledger_repair_required,
        manifest_sha256=equivalence_manifest_digest(manifest),
    )


def evaluate_staging_preflight(
    *,
    repository_versions: list[str],
    remote_versions: list[str],
    manifest: dict[str, Any],
    migrations_dir: Path,
) -> ConvergencePlan:
    """Run hash verification and return a deterministic staging deploy plan."""
    verify_alias_hashes(migrations_dir=migrations_dir, manifest=manifest)
    return classify_staging_ledger(
        repository_versions=repository_versions,
        remote_versions=remote_versions,
        manifest=manifest,
    )


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
    parser.add_argument(
        "--equivalence-manifest",
        type=Path,
        default=Path("scripts/ci/staging-migration-equivalence.json"),
    )
    parser.add_argument("--print-manifest", action="store_true")
    parser.add_argument("--staging-preflight", action="store_true")
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--json-plan", action="store_true")
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
        repository_versions = [migration.version for migration in migrations]
        cohort_manifest = load_cohorts(args.cohorts_file)
        assert_v1_profile(cohort_manifest)

        if args.print_manifest:
            print(
                json.dumps(
                    {
                        "migration_count": len(migrations),
                        "migration_tip": migrations[-1].version,
                        "manifest_sha256": manifest_digest(migrations, cohort_manifest),
                        "v1_release_profile": cohort_manifest["v1_release_profile"],
                        "cohorts": cohort_manifest["cohorts"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if args.staging_preflight:
            if not all((args.target_kind, args.target_project_ref, args.ledger_file)):
                raise SchemaConvergenceError(
                    "staging-preflight requires target-kind, target-project-ref, and ledger-file"
                )
            if args.ledger_source != "live-query":
                raise SchemaConvergenceError(
                    "ledger-source=live-query is required for staging deploy preflight"
                )
            assert_sandbox_target(
                target_kind=args.target_kind,
                target_project_ref=args.target_project_ref,
            )
            if not args.ledger_file.is_file():
                raise SchemaConvergenceError(f"remote ledger file not found: {args.ledger_file}")
            equivalence = load_equivalence_manifest(
                args.equivalence_manifest,
                expected_source_sha=args.expected_source_sha,
            )
            remote_versions = parse_ledger(args.ledger_file.read_text(encoding="utf-8"))
            plan = evaluate_staging_preflight(
                repository_versions=repository_versions,
                remote_versions=remote_versions,
                manifest=equivalence,
                migrations_dir=args.migrations_dir,
            )
            if plan.unresolved_remote_versions:
                raise SchemaConvergenceError(
                    "unresolved remote migration versions: "
                    + ", ".join(plan.unresolved_remote_versions)
                )
            if args.json_plan:
                print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
            else:
                print(json.dumps(plan.as_dict(), sort_keys=True))
            if plan.ledger_repair_required:
                print(f"::error::{STAGING_LEDGER_REPAIR_REQUIRED}", file=sys.stderr)
                return 1
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
            manifest=cohort_manifest,
            cohort_id=args.cohort,
            repository_versions=repository_versions,
            remote_versions=remote_versions,
        )
    except SchemaConvergenceError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(
        "schema convergence rehearsal OK: "
        f"cohort={args.cohort} ledger_tip={remote_versions[-1]} pending_after={len(pending)} "
        f"manifest_sha256={manifest_digest(migrations, cohort_manifest)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
