#!/usr/bin/env python3
"""Prove five immutable transaction migrations in the existing typegen stack.

This runner has no hosted mode or caller-supplied connection string. It starts
the marked disposable Supabase workdir, uses only its fixed loopback database,
and restores the complete source copy before the job's normal full reset.
Only source copies in that temporary workdir are hidden; repository SQL bytes
are never rewritten. All raw SQL, ledger values, and subprocess logs stay in
memory and are never printed or uploaded.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from typing import Iterator

from explicit_transaction_boundary import (
    BOUND_FILES,
    Boundary,
    BoundaryError,
    parse_bound_file,
    verify_disposable_prefix,
)

ROOT = Path(__file__).resolve().parents[2]
FIRST = next(iter(BOUND_FILES))
LAST = next(reversed(BOUND_FILES))
PROJECT = "vergeo5-typegen"
CONTAINER = "supabase_db_vergeo5-typegen"
NETWORK = "supabase_network_vergeo5-typegen"
NETWORK_BIND_OPTION = "com.docker.network.bridge.host_binding_ipv4"
NETWORK_OWNER_LABEL = "org.convergeo.typegen.disposable"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.143"
URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres?sslmode=disable"
LOCK = Path("/tmp/convergeo-typegen-explicit-window.lock")
OWNERSHIP_MARKER = ".owned-typegen-stack"
ADOPTION = "20260929120003"
LEDGER_COLUMNS = "version,name,statements,created_by,idempotency_key,rollback"
STAGES = frozenset(
    {
        "entry",
        "source_inventory",
        "checkout_identity",
        "suffix_order",
        "cli_version",
        "scratch_directory",
        "stack_ownership",
        "network_binding",
        "prefix_copy",
        "cli_start",
        "container_identity",
        "prefix_reset",
        "prefix_ledger",
        "cli_reference_push",
        "cli_reference_check",
        "predecessor_reset",
        "predecessor_ledger",
        "suffix_replay",
        "final_ledger",
        "full_reset",
        "full_ledger",
    }
)
ERROR_CODES = frozenset(
    {
        "BOUNDARY_REJECTED",
        "CLI_REFERENCE_MISMATCH",
        "CLI_VERSION_MISMATCH",
        "COMMAND_FAILED",
        "COMMAND_UNAVAILABLE",
        "CONTAINER_MISMATCH",
        "CONTAINER_MISSING",
        "GUARD_REJECTED",
        "HISTORY_MISMATCH",
        "IMAGE_MISMATCH",
        "SOURCE_MISMATCH",
        "SQL_FAILED",
        "SQL_UNAVAILABLE",
        "UNEXPECTED_EXCEPTION",
        "VERSION_MISMATCH",
        "WORKDIR_UNAVAILABLE",
    }
)


class RehearsalError(RuntimeError):
    """A bounded disposable proof failed without exposing database contents."""

    def __init__(self, message: str, *, code: str = "GUARD_REJECTED") -> None:
        if code not in ERROR_CODES:
            raise ValueError("unreviewed disposable proof error code")
        super().__init__(message)
        self.code = code


@dataclass
class StageTracker:
    current: str = "entry"

    def enter(self, stage: str) -> None:
        if stage not in STAGES:
            raise ValueError("unreviewed disposable proof stage")
        self.current = stage
        print(f"proof_stage|{stage}|BEGIN", file=sys.stderr, flush=True)


def failure_marker(tracker: StageTracker, exc: Exception) -> str:
    """Emit only fixed labels; exception messages may contain database output."""
    stage = tracker.current if tracker.current in STAGES else "entry"
    if isinstance(exc, RehearsalError):
        code = exc.code
    elif isinstance(exc, BoundaryError):
        code = "BOUNDARY_REJECTED"
    elif isinstance(exc, OSError) and tracker.current in {
        "scratch_directory",
        "stack_ownership",
        "prefix_copy",
    }:
        code = "WORKDIR_UNAVAILABLE"
    else:
        code = "UNEXPECTED_EXCEPTION"
    if code not in ERROR_CODES:
        code = "UNEXPECTED_EXCEPTION"
    return f"error: bounded disposable proof failed: stage={stage} code={code}"


def checked(args: list[str], *, data: bytes | None = None, timeout: int = 600) -> bytes:
    try:
        result = subprocess.run(
            args, input=data, capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RehearsalError(
            f"disposable command unavailable: {Path(args[0]).name}",
            code="COMMAND_UNAVAILABLE",
        ) from exc
    if result.returncode:
        raise RehearsalError(
            f"disposable command failed: {Path(args[0]).name} ({result.returncode})",
            code="COMMAND_FAILED",
        )
    return result.stdout.strip()


def sql(container: str, query: str, *, expected_failure: bool = False) -> bytes:
    args = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-X",
        "-q",
        "-A",
        "-t",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    try:
        result = subprocess.run(
            args, input=query.encode(), capture_output=True, timeout=300, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RehearsalError(
            "disposable SQL command unavailable", code="SQL_UNAVAILABLE"
        ) from exc
    if expected_failure:
        if result.returncode == 0 or b"disposable history refusal" not in result.stderr:
            raise RehearsalError(
                "injected history refusal was not the observed failure"
            )
    elif result.returncode:
        raise RehearsalError(
            f"disposable SQL failed ({result.returncode})", code="SQL_FAILED"
        )
    return result.stdout.strip()


def cli(workdir: Path, *args: str) -> None:
    checked(["supabase", "--workdir", str(workdir), "db", *args], timeout=900)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def catalog_hash(container: str) -> str:
    """Hash the fixture's complete schema, including ACLs, without emitting it."""
    return digest(
        checked(
            [
                "docker",
                "exec",
                container,
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "--schema-only",
                "--restrict-key=ConvergeoTypegenCatalog",
            ]
        )
    )


def ledger(container: str, versions: list[str] | None = None) -> list[list[object]]:
    predicate = (
        "true"
        if versions is None
        else "version IN (" + ",".join(f"'{v}'" for v in versions) + ")"
    )
    if versions is not None and any(
        re.fullmatch(r"[0-9]+", v) is None for v in versions
    ):
        raise RehearsalError("unreviewed migration version")
    raw = sql(
        container,
        f"""
SELECT coalesce(jsonb_agg(jsonb_build_array({LEDGER_COLUMNS}) ORDER BY version), '[]'::jsonb)
FROM supabase_migrations.schema_migrations WHERE {predicate};
""",
    )
    try:
        rows = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise RehearsalError("malformed disposable history") from exc
    if not isinstance(rows, list) or any(
        not isinstance(row, list) or len(row) != 6 for row in rows
    ):
        raise RehearsalError("unexpected disposable history shape")
    return rows


def target_container() -> str:
    matches = (
        checked(
            ["docker", "ps", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.ID}}"]
        )
        .decode()
        .splitlines()
    )
    if len(matches) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", matches[0]):
        raise RehearsalError(
            "unique marked typegen container is missing", code="CONTAINER_MISSING"
        )
    container = matches[0]
    details = json.loads(
        checked(["docker", "inspect", container, "--format", "{{json .}}"])
    )
    ports = details["NetworkSettings"]["Ports"].get("5432/tcp")
    if details["Config"]["Image"] != IMAGE:
        raise RehearsalError("typegen image changed", code="IMAGE_MISMATCH")
    if (
        details["Name"] != f"/{CONTAINER}"
        or not details["State"]["Running"]
        or ports != [{"HostIp": "127.0.0.1", "HostPort": "54322"}]
    ):
        raise RehearsalError(
            "typegen container identity or loopback binding changed",
            code="CONTAINER_MISMATCH",
        )
    if sql(container, "SHOW server_version_num;") != b"170006":
        raise RehearsalError(
            "qualified PostgreSQL patch changed", code="VERSION_MISMATCH"
        )
    return container


def network_details(network_id: str) -> dict:
    if re.fullmatch(r"[0-9a-f]{64}", network_id) is None:
        raise RehearsalError("invalid disposable network ID", code="CONTAINER_MISMATCH")
    details = json.loads(
        checked(["docker", "network", "inspect", network_id, "--format", "{{json .}}"])
    )
    if (
        details.get("Id") != network_id
        or details.get("Name") != NETWORK
        or details.get("Driver") != "bridge"
        or details.get("Labels", {}).get("com.supabase.cli.project") != PROJECT
        or details.get("Labels", {}).get(NETWORK_OWNER_LABEL) != "1"
    ):
        raise RehearsalError(
            "disposable network identity changed", code="CONTAINER_MISMATCH"
        )
    return details


def bind_disposable_network(state: WindowState) -> None:
    """Set the pinned CLI's otherwise unspecified host binding to loopback.

    CLI 2.109.1 publishes DB with HostPort only and reuses an existing named
    network. The bridge option affects its default host IP without changing
    the CLI image, database URL, or the strict post-start container guard.
    """
    if checked(
        [
            "docker",
            "network",
            "ls",
            "--filter",
            f"name=^{NETWORK}$",
            "--format",
            "{{.ID}}",
        ]
    ).strip():
        raise RehearsalError(
            "disposable network already exists", code="CONTAINER_MISMATCH"
        )
    network_id = checked(
        [
            "docker",
            "network",
            "create",
            "--driver",
            "bridge",
            "--opt",
            f"{NETWORK_BIND_OPTION}=127.0.0.1",
            "--label",
            f"com.supabase.cli.project={PROJECT}",
            "--label",
            f"{NETWORK_OWNER_LABEL}=1",
            NETWORK,
        ]
    ).decode()
    if re.fullmatch(r"[0-9a-f]{64}", network_id) is None:
        raise RehearsalError(
            "disposable network ID is invalid", code="CONTAINER_MISMATCH"
        )
    state.owned_network = network_id
    details = network_details(network_id)
    if (
        details.get("Options", {}).get(NETWORK_BIND_OPTION) != "127.0.0.1"
        or details.get("Containers") != {}
    ):
        raise RehearsalError(
            "disposable network is not loopback-only and empty",
            code="CONTAINER_MISMATCH",
        )


def started_container_on_network(network_id: str) -> str:
    """Identify the just-created CLI container before checking its port mapping."""
    matches = (
        checked(
            ["docker", "ps", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.ID}}"]
        )
        .decode()
        .splitlines()
    )
    if len(matches) != 1 or re.fullmatch(r"[0-9a-f]{12,64}", matches[0]) is None:
        raise RehearsalError(
            "new disposable database is missing", code="CONTAINER_MISSING"
        )
    details = json.loads(
        checked(["docker", "inspect", matches[0], "--format", "{{json .}}"])
    )
    network = details.get("NetworkSettings", {}).get("Networks", {}).get(NETWORK, {})
    if details.get("Config", {}).get("Image") != IMAGE:
        raise RehearsalError("new disposable image changed", code="IMAGE_MISMATCH")
    if (
        not details.get("Id", "").startswith(matches[0])
        or details.get("Name") != f"/{CONTAINER}"
        or details.get("Config", {}).get("Labels", {}).get("com.supabase.cli.project")
        != PROJECT
        or not details.get("State", {}).get("Running")
        or network.get("NetworkID") != network_id
    ):
        raise RehearsalError(
            "new disposable database ownership changed", code="CONTAINER_MISMATCH"
        )
    return matches[0]


def source_inventory(workdir: Path) -> tuple[list[Path], int]:
    config = workdir / "supabase/config.toml"
    try:
        with config.open("rb") as handle:
            parsed = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RehearsalError(
            "disposable profile config is unavailable or malformed",
            code="SOURCE_MISMATCH",
        ) from exc
    db = parsed.get("db")
    seed = db.get("seed") if isinstance(db, dict) else None
    if (
        parsed.get("project_id") != PROJECT
        or not isinstance(db, dict)
        or db.get("major_version") != 17
        or not isinstance(seed, dict)
        or seed.get("enabled") is not False
        or db.get("port") != 54322
    ):
        raise RehearsalError(
            "workdir is not the reviewed disposable profile", code="SOURCE_MISMATCH"
        )
    files = sorted((workdir / "supabase/migrations").glob("*.sql"))
    committed = sorted((ROOT / "supabase/migrations").glob("*.sql"))
    if len(files) != 139 or [p.name for p in files] != [p.name for p in committed]:
        raise RehearsalError(
            "disposable copy does not match 139 source migrations",
            code="SOURCE_MISMATCH",
        )
    for source, copy in zip(committed, files, strict=True):
        try:
            matches = digest(source.read_bytes()) == digest(copy.read_bytes())
        except OSError as exc:
            raise RehearsalError(
                "disposable migration source is unreadable", code="SOURCE_MISMATCH"
            ) from exc
        if not matches:
            raise RehearsalError(
                "disposable migration copy changed", code="SOURCE_MISMATCH"
            )
    if not any(p.name.startswith(ADOPTION + "_") for p in files):
        raise RehearsalError(
            "service adoption predecessor is missing", code="SOURCE_MISMATCH"
        )
    for name in BOUND_FILES:
        parse_bound_file(name)
    if FIRST not in [p.name for p in files]:
        raise RehearsalError(
            "reviewed migration boundary is missing", code="SOURCE_MISMATCH"
        )
    return files, [p.name for p in files].index(FIRST)


@contextmanager
def visible_prefix(files: list[Path], through: int, holding: Path) -> Iterator[None]:
    """Hide only temporary copies after through; restore even on failure."""
    hidden = files[through + 1 :]
    moved: list[Path] = []
    try:
        for path in hidden:
            os.replace(path, holding / path.name)
            moved.append(path)
        yield
    finally:
        for path in moved:
            os.replace(holding / path.name, path)


@dataclass
class WindowState:
    owned_network: str | None = None
    owned_container: str | None = None


def mark_owned(workdir: Path, state: WindowState, container: str) -> None:
    if re.fullmatch(r"[0-9a-f]{12,64}", container) is None:
        raise RehearsalError("invalid owned container ID")
    state.owned_container = container
    (workdir / OWNERSHIP_MARKER).write_text(container + "\n", encoding="ascii")


@contextmanager
def owned_window(workdir: Path, files: list[Path]) -> Iterator[WindowState]:
    """Hold the fixed lock through any cleanup of the stack this run started."""
    with LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if checked(
            ["docker", "ps", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.ID}}"]
        ).strip():
            raise RehearsalError(
                "typegen stack must be newly created by this proof",
                code="CONTAINER_MISMATCH",
            )
        state = WindowState()
        try:
            yield state
        except BaseException:
            if state.owned_container is not None:
                try:
                    verified, _ = source_inventory(workdir)
                    if verified != files or target_container() != state.owned_container:
                        raise RehearsalError("owned disposable target changed")
                    cli(workdir, "reset", "--no-seed")
                    restored_container = target_container()
                    mark_owned(workdir, state, restored_container)
                    if len(ledger(restored_container)) != len(files):
                        raise RehearsalError(
                            "failure cleanup did not restore full history"
                        )
                    print("failure_cleanup|restored_139|PASS")
                except Exception:
                    print(
                        "error: disposable failure cleanup could not restore 139 migrations",
                        file=sys.stderr,
                    )
            elif state.owned_network is not None:
                try:
                    matches = (
                        checked(
                            [
                                "docker",
                                "network",
                                "ls",
                                "--filter",
                                f"name=^{NETWORK}$",
                                "--format",
                                "{{.ID}}",
                            ]
                        )
                        .decode()
                        .splitlines()
                    )
                    if matches:
                        if len(matches) != 1 or not state.owned_network.startswith(
                            matches[0]
                        ):
                            raise RehearsalError("owned network ID changed")
                        details = network_details(state.owned_network)
                        if details.get("Containers") != {}:
                            raise RehearsalError("owned network is not empty")
                        checked(["docker", "network", "rm", state.owned_network])
                except Exception:
                    print(
                        "error: owned disposable network could not be removed",
                        file=sys.stderr,
                    )
            raise


def assert_prefix(container: str, expected: list[list[object]], count: int) -> None:
    current = ledger(container)
    if len(current) < count or current[:count] != expected[:count]:
        raise RehearsalError(
            "predecessor migration history changed", code="HISTORY_MISMATCH"
        )


def rejection_trigger(container: str, version: str, *, create: bool) -> None:
    if re.fullmatch(r"[0-9]+", version) is None:
        raise RehearsalError("unreviewed trigger version")
    if create:
        sql(
            container,
            f"""
CREATE FUNCTION supabase_migrations.reject_explicit_fixture() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
  IF NEW.version = '{version}' THEN RAISE EXCEPTION 'disposable history refusal'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER reject_explicit_fixture BEFORE INSERT
ON supabase_migrations.schema_migrations FOR EACH ROW
EXECUTE FUNCTION supabase_migrations.reject_explicit_fixture();
""",
        )
    else:
        sql(
            container,
            """
DROP TRIGGER reject_explicit_fixture ON supabase_migrations.schema_migrations;
DROP FUNCTION supabase_migrations.reject_explicit_fixture();
""",
        )


def commit_without_ack(container: str, version: str, body: bytes) -> None:
    """Observe committed fixture history, then cut the psql acknowledgement."""
    args = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-X",
        "-q",
        "-A",
        "-t",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    with TemporaryFile() as payload:
        payload.write(body + b"\nSELECT pg_sleep(30);\n")
        payload.seek(0)
        process = subprocess.Popen(
            args,
            stdin=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if len(ledger(container, [version])) == 1:
                    if process.poll() is not None:
                        raise RehearsalError(
                            "fixture client finished before acknowledgement was cut"
                        )
                    process.terminate()
                    process.wait(timeout=5)
                    if process.returncode == 0:
                        raise RehearsalError(
                            "fixture client did not lose acknowledgement"
                        )
                    return
                if process.poll() is not None:
                    raise RehearsalError("fixture body failed before committed history")
                time.sleep(0.1)
            raise RehearsalError("timed out waiting for committed fixture history")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def check_cli_reference(
    container: str, files: list[Path], first_index: int
) -> list[list[object]]:
    rows = ledger(container)
    expected_versions = [path.stem.split("_", 1)[0] for path in files]
    if [row[0] for row in rows] != expected_versions:
        raise RehearsalError(
            "pinned CLI did not apply the complete source suffix",
            code="CLI_REFERENCE_MISMATCH",
        )
    for filename in BOUND_FILES:
        boundary = parse_bound_file(filename)
        matches = [row for row in rows if row[0] == boundary.version]
        if matches != [expected_history_row(boundary)]:
            raise RehearsalError(
                f"pinned CLI six-column history differs for {filename}",
                code="CLI_REFERENCE_MISMATCH",
            )
    print(f"cli_statement_serialization|PASS|{len(BOUND_FILES)}")
    return rows[:first_index]


def expected_history_row(boundary: Boundary) -> list[object]:
    row = list(boundary.disposable_history_row())
    row[2] = list(row[2])
    return row


def run(workdir: Path, tracker: StageTracker | None = None) -> None:
    tracker = tracker or StageTracker()
    tracker.enter("source_inventory")
    files, first_index = source_inventory(workdir)
    tracker.enter("checkout_identity")
    source = checked(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode()
    tree = checked(["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"]).decode()
    if (
        re.fullmatch(r"[0-9a-f]{40}", source) is None
        or re.fullmatch(r"[0-9a-f]{40}", tree) is None
        or (
            os.environ.get("QUALIFICATION_SHA")
            and os.environ["QUALIFICATION_SHA"] != source
        )
    ):
        raise RehearsalError(
            "qualified checkout identity changed", code="SOURCE_MISMATCH"
        )
    tracker.enter("suffix_order")
    if (
        files[-1].name != "20261006160000_service_table_acl_hardening.sql"
        or files[-2].name != LAST
    ):
        raise RehearsalError("reviewed suffix order changed", code="SOURCE_MISMATCH")
    tracker.enter("cli_version")
    if checked(["supabase", "--version"]).decode().splitlines()[0] != "2.109.1":
        raise RehearsalError("pinned Supabase CLI changed", code="CLI_VERSION_MISMATCH")
    tracker.enter("scratch_directory")
    with TemporaryDirectory(prefix="typegen-explicit-", dir=workdir) as scratch:
        holding = Path(scratch)
        tracker.enter("stack_ownership")
        with owned_window(workdir, files) as window:
            tracker.enter("network_binding")
            bind_disposable_network(window)
            tracker.enter("prefix_copy")
            with visible_prefix(files, first_index - 1, holding):
                tracker.enter("cli_start")
                cli(workdir, "start")
                tracker.enter("container_identity")
                if window.owned_network is None:
                    raise RehearsalError("disposable network ownership is missing")
                mark_owned(
                    workdir,
                    window,
                    started_container_on_network(window.owned_network),
                )
                container = target_container()
                if container != window.owned_container:
                    raise RehearsalError("new disposable database ID changed")
                tracker.enter("prefix_reset")
                cli(workdir, "reset", "--no-seed")
                tracker.enter("container_identity")
                container = target_container()
                mark_owned(workdir, window, container)
                tracker.enter("prefix_ledger")
                prefix = ledger(container)
                expected_prefix = [
                    path.stem.split("_", 1)[0] for path in files[:first_index]
                ]
                if [
                    row[0] for row in prefix
                ] != expected_prefix or ADOPTION not in expected_prefix:
                    raise RehearsalError(
                        "predecessor ledger is incomplete", code="HISTORY_MISMATCH"
                    )
            # Native pinned CLI execution establishes the statement arrays.
            tracker.enter("cli_reference_push")
            cli(workdir, "push", "--db-url", URL, "--include-all", "--yes")
            tracker.enter("cli_reference_check")
            baseline = check_cli_reference(container, files, first_index)
            # Recreate the exact predecessor state. Never test on the final schema.
            tracker.enter("predecessor_reset")
            with visible_prefix(files, first_index - 1, holding):
                cli(workdir, "reset", "--no-seed")
                tracker.enter("container_identity")
                container = target_container()
                mark_owned(workdir, window, container)
                tracker.enter("predecessor_ledger")
                assert_prefix(container, baseline, first_index)
                if len(ledger(container)) != first_index:
                    raise RehearsalError(
                        "predecessor reset retained suffix history",
                        code="HISTORY_MISMATCH",
                    )
            completed: list[list[object]] = []
            for index in range(first_index, len(files)):
                tracker.enter("suffix_replay")
                path = files[index]
                before = ledger(container)
                if [row[0] for row in before] != [
                    prior.stem.split("_", 1)[0] for prior in files[:index]
                ]:
                    raise RehearsalError(
                        "unexpected migration history before body",
                        code="HISTORY_MISMATCH",
                    )
                assert_prefix(container, baseline, first_index)
                if path.name in BOUND_FILES:
                    boundary = parse_bound_file(path.name)
                    if path.read_bytes() != boundary.raw:
                        raise RehearsalError(
                            "original body copy changed", code="SOURCE_MISMATCH"
                        )
                    rejection_trigger(container, boundary.version, create=True)
                    before_catalog = catalog_hash(container)
                    sql(
                        container,
                        boundary.with_disposable_history_before_commit().decode(),
                        expected_failure=True,
                    )
                    after_catalog = catalog_hash(container)
                    if before_catalog != after_catalog or ledger(container) != before:
                        raise RehearsalError(
                            "original body or history escaped failed transaction"
                        )
                    rejection_trigger(container, boundary.version, create=False)
                    # Cut the client's acknowledgement after commit, then
                    # establish the exact row before attempting any retry.
                    commit_without_ack(
                        container,
                        boundary.version,
                        boundary.with_disposable_history_before_commit(),
                    )
                    current = ledger(container, [boundary.version])
                    expected_row = expected_history_row(boundary)
                    if current != [expected_row]:
                        raise RehearsalError(
                            "successful body has an untruthful six-column ledger"
                        )
                    completed.append(current[0])
                    verify_disposable_prefix(completed)
                    with visible_prefix(files, index, holding):
                        stable = catalog_hash(container)
                        cli(workdir, "push", "--db-url", URL, "--include-all", "--yes")
                        if (
                            catalog_hash(container) != stable
                            or ledger(container) != before + current
                        ):
                            raise RehearsalError(
                                "lost-ack resume changed a committed migration"
                            )
                    print(
                        f"original_body_atomicity|{boundary.version}|PASS|{before_catalog}|{after_catalog}"
                    )
                else:
                    # Let pinned CLI apply the two intervening migrations and
                    # final ACL hardening in order, using the same workdir.
                    with visible_prefix(files, index, holding):
                        cli(workdir, "push", "--db-url", URL, "--include-all", "--yes")
                    assert_prefix(container, baseline, first_index)
                    if [row[0] for row in ledger(container)] != [
                        p.stem.split("_", 1)[0] for p in files[: index + 1]
                    ]:
                        raise RehearsalError("intervening CLI migration order changed")
            tracker.enter("final_ledger")
            if len(ledger(container)) != len(files):
                raise RehearsalError(
                    "original-body rehearsal did not finish the source suffix"
                )
            assert_prefix(container, baseline, first_index)
            # Restore the job's ordinary qualified profile for typegen and ACLs.
            tracker.enter("full_reset")
            cli(workdir, "reset", "--no-seed")
            tracker.enter("container_identity")
            container = target_container()
            mark_owned(workdir, window, container)
            tracker.enter("full_ledger")
            if len(ledger(container)) != len(files):
                raise RehearsalError(
                    "normal full replay did not restore 139 migrations"
                )
            print(f"qualified_source|{source}|{tree}")
            print("qualified_original_body_replay|PASS|5")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: rehearse_explicit_transaction_profile.py DISPOSABLE_WORKDIR"
        )
    workdir = Path(sys.argv[1]).resolve()
    tracker = StageTracker()
    try:
        run(workdir, tracker)
    except Exception as exc:
        print(failure_marker(tracker, exc), file=sys.stderr)
        raise SystemExit(1) from exc
