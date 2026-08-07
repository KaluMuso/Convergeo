#!/usr/bin/env python3
"""Reconcile repository migrations against remote schema_migrations.

After ``supabase db push --include-all``, every local migration version must be
present on the linked remote database. Compares version prefixes derived from
``supabase/migrations/*.sql`` filenames (sorted) against remote versions — no
hard-coded migration numbers, so new migrations cannot bypass this check.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MIGRATION_FILE_RE = re.compile(r"^(.+?)_.+\.sql$")


class MigrationReconcileError(ValueError):
    """Raised when repository and remote migration ledgers diverge."""


def repo_migration_versions(migrations_dir: Path) -> list[str]:
    """Sorted version prefixes from local migration filenames."""
    if not migrations_dir.is_dir():
        raise MigrationReconcileError(f"migrations dir not found: {migrations_dir}")

    versions: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_FILE_RE.match(path.name)
        if not match:
            raise MigrationReconcileError(f"unexpected migration filename: {path.name}")
        versions.append(match.group(1))

    if not versions:
        raise MigrationReconcileError(f"no migrations in {migrations_dir}")

    return versions


def parse_remote_versions(raw: str) -> list[str]:
    """Parse remote versions from psql -tA output or one-version-per-line text."""
    versions: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # migration list table rows may include pipes — keep first token only.
        token = line.split("|", 1)[0].strip()
        if token:
            versions.append(token)
    return versions


def parse_migration_list_table(raw: str) -> tuple[list[str], list[str]]:
    """Parse ``supabase migration list`` Glamour table into local/remote columns."""
    local: list[str] = []
    remote: list[str] = []
    for line in raw.splitlines():
        if "│" not in line:
            continue
        if line.strip().startswith("─") or "LOCAL" in line:
            continue
        parts = [part.strip() for part in line.split("│")]
        if len(parts) < 2:
            continue
        local_cell = parts[0]
        remote_cell = parts[1]
        if local_cell:
            local.append(local_cell)
        if remote_cell:
            remote.append(remote_cell)
    return local, remote


def reconcile_versions(repo_versions: list[str], remote_versions: list[str]) -> None:
    """Fail when any repo migration is missing on remote or counts diverge."""
    repo_set = set(repo_versions)
    remote_set = set(remote_versions)

    missing_on_remote = [v for v in repo_versions if v not in remote_set]
    if missing_on_remote:
        raise MigrationReconcileError(
            "remote missing repository migrations: " + ", ".join(missing_on_remote)
        )

    extra_on_remote = sorted(remote_set - repo_set)
    if extra_on_remote:
        raise MigrationReconcileError(
            "remote has migrations absent from repository: " + ", ".join(extra_on_remote)
        )

    if len(remote_versions) < len(repo_versions):
        raise MigrationReconcileError(
            f"remote count {len(remote_versions)} < repository count {len(repo_versions)}"
        )

    repo_tip = repo_versions[-1]
    remote_tip = sorted(remote_versions)[-1] if remote_versions else ""
    if remote_tip != repo_tip:
        raise MigrationReconcileError(
            f"remote tip {remote_tip!r} != repository tip {repo_tip!r}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile repo vs remote migrations")
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path("supabase/migrations"),
    )
    parser.add_argument(
        "--remote-versions-file",
        type=Path,
        help="File with remote versions (psql -tA, one per line)",
    )
    parser.add_argument(
        "--migration-list-file",
        type=Path,
        help="File with ``supabase migration list`` table output",
    )
    args = parser.parse_args(argv)

    try:
        repo_versions = repo_migration_versions(args.migrations_dir)
    except MigrationReconcileError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    if args.remote_versions_file:
        raw = args.remote_versions_file.read_text(encoding="utf-8")
        remote_versions = parse_remote_versions(raw)
    elif args.migration_list_file:
        raw = args.migration_list_file.read_text(encoding="utf-8")
        _local, remote_versions = parse_migration_list_table(raw)
        if not remote_versions:
            remote_versions = parse_remote_versions(raw)
    else:
        print(
            "::error::--remote-versions-file or --migration-list-file is required",
            file=sys.stderr,
        )
        return 1

    try:
        reconcile_versions(repo_versions, remote_versions)
    except MigrationReconcileError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    tip = repo_versions[-1]
    print(f"migration reconcile OK: {len(repo_versions)} versions, tip={tip}")
    return 0


if __name__ == "__main__":
  raise SystemExit(main())
