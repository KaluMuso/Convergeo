#!/usr/bin/env python3
"""Probe Supabase CLI 2.109.1 migration atomicity on an owned local Postgres.

This is a manual, source-bound diagnostic. It never connects to a hosted DB,
creates a Supabase project, or changes the original migration files. The
synthetic SQL has the same top-level BEGIN/COMMIT boundary as the five bound
source files, and failure injection targets the CLI's history insert.

Usage: python3 scripts/ci/probe_pinned_cli_explicit_transactions.py /path/to/supabase-go [--pg17]
Requires an already available local Docker image; no image pull.
"""

from __future__ import annotations

import fcntl
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from explicit_transaction_boundary import BOUND_FILES, parse_bound_file

ROOT = Path(__file__).resolve().parents[2]
IMAGES = {
    "--pg15": "postgres:15-alpine",
    "--pg17": "pgvector/pgvector:0.8.0-pg17-trixie",
}
VERSION = "20261006000000"


def call(*args: str, input_text: str | None = None, timeout: int = 30) -> str:
    result = subprocess.run(
        args,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip()[:300] if args[0] == "docker" else ""
        raise RuntimeError(
            f"local diagnostic command failed: {args[0]} ({result.returncode}) {detail}"
        )
    return result.stdout.strip()


def bind_source() -> None:
    for filename in BOUND_FILES:
        parse_bound_file(filename)


def sql(container: str, database: str, statement: str) -> str:
    return call(
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        database,
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-Atq",
        input_text=statement,
    )


def counts(container: str, database: str) -> tuple[int, int]:
    result = sql(
        container,
        database,
        f"SELECT (SELECT count(*) FROM public.atomicity_probe), "
        f"(SELECT count(*) FROM supabase_migrations.schema_migrations WHERE version='{VERSION}');",
    )
    left, right = result.split("|")
    return int(left), int(right)


def setup_database(container: str, database: str) -> None:
    sql(container, "postgres", f"CREATE DATABASE {database};")
    sql(
        container,
        database,
        """
CREATE SCHEMA supabase_migrations;
CREATE TABLE supabase_migrations.schema_migrations (
  version text NOT NULL PRIMARY KEY, statements text[], name text,
  created_by text, idempotency_key text UNIQUE, rollback text[]
);
CREATE TABLE public.atomicity_probe (id integer PRIMARY KEY);
""",
    )


def project(cli: str, directory: Path, label: str, migration: str) -> Path:
    target = directory / label
    target.mkdir()
    call(cli, "init", "--workdir", str(target), "--yes")
    migrations = target / "supabase/migrations"
    migrations.mkdir(exist_ok=True)
    (migrations / f"{VERSION}_{label}.sql").write_text(migration)
    return target


def push(
    cli: str,
    container: str,
    database: str,
    target: Path,
    port: int,
    *,
    stop_after_commit: bool = False,
) -> tuple[int, str]:
    url = f"postgresql://postgres:postgres@127.0.0.1:{port}/{database}?sslmode=disable"
    args = [
        cli,
        "db",
        "push",
        "--db-url",
        url,
        "--workdir",
        str(target),
        "--include-all",
        "--yes",
        "--debug",
    ]
    log = target / "cli.log"
    with log.open("w+") as output:
        proc = subprocess.Popen(
            args, stdout=output, stderr=subprocess.STDOUT, text=True
        )
        deadline = time.monotonic() + 25
        while proc.poll() is None and time.monotonic() < deadline:
            if stop_after_commit and counts(container, database) == (1, 1):
                # Simulate losing the command's final acknowledgement after DB commit.
                proc.terminate()
                break
            time.sleep(0.1)
        try:
            code = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait(timeout=3)
        output.seek(0)
        observed = output.read()
    # A first local connection may attempt TLS even with sslmode=disable.
    # Retry that transport-only failure once; never retry after any SQL ran.
    if "tls error (server refused TLS connection)" in observed:
        if counts(container, database) != (0, 0):
            raise RuntimeError("TLS failure occurred after a local write")
        with log.open("w+") as output:
            proc = subprocess.Popen(
                args, stdout=output, stderr=subprocess.STDOUT, text=True
            )
            deadline = time.monotonic() + 25
            while proc.poll() is None and time.monotonic() < deadline:
                if stop_after_commit and counts(container, database) == (1, 1):
                    proc.terminate()
                    break
                time.sleep(0.1)
            try:
                code = proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait(timeout=3)
            output.seek(0)
            observed = output.read()
    return code, observed


def expect(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(f"local CLI atomicity probe failed: {label}")


def main(cli: str, image: str) -> None:
    bind_source()
    expect(call(cli, "--version").splitlines()[0] == "2.109.1", "pinned CLI version")
    call("docker", "image", "inspect", image)
    container = "pr718-cli-atomicity-" + uuid4().hex[:12]
    try:
        call(
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-p",
            "127.0.0.1::5432",
            image,
        )
        ready_streak = 0
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_isready",
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                ],
                capture_output=True,
                check=False,
            )
            if ready.returncode == 0:
                ready_streak += 1
                if ready_streak >= 12:
                    break
            else:
                ready_streak = 0
            time.sleep(0.25)
        else:
            raise RuntimeError("owned disposable PostgreSQL did not become ready")
        server_version_num = sql(container, "postgres", "SHOW server_version_num;")
        wanted_major = "17" if image == IMAGES["--pg17"] else "15"
        expect(
            server_version_num.startswith(wanted_major), "disposable PostgreSQL major"
        )
        print(f"server_version_num={server_version_num}")
        port = int(call("docker", "port", container, "5432/tcp").rsplit(":", 1)[1])
        with tempfile.TemporaryDirectory(prefix="pr718-cli-atomicity-") as scratch:
            work = Path(scratch)
            scenarios = {
                "before_sql": (
                    "DO $$ BEGIN RAISE EXCEPTION 'before SQL'; END $$;\n"
                    "BEGIN;\nINSERT INTO public.atomicity_probe VALUES (1);\nCOMMIT;\n",
                    (0, 0),
                ),
                "mid_file": (
                    "BEGIN;\nINSERT INTO public.atomicity_probe VALUES (1);\n"
                    "DO $$ BEGIN RAISE EXCEPTION 'mid file'; END $$;\nCOMMIT;\n",
                    (0, 0),
                ),
                "history_refusal": (
                    "BEGIN;\nINSERT INTO public.atomicity_probe VALUES (1);\nCOMMIT;\n",
                    (1, 0),
                ),
                "lost_ack": (
                    "BEGIN;\nINSERT INTO public.atomicity_probe VALUES (1);\nCOMMIT;\n",
                    (1, 1),
                ),
            }
            lock = work / "whole-window.lock"
            for label, (migration, wanted) in scenarios.items():
                database = "probe_" + label
                setup_database(container, database)
                target = project(cli, work, label, migration)
                if label == "history_refusal":
                    sql(
                        container,
                        database,
                        f"""
CREATE FUNCTION public.reject_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.version = '{VERSION}' THEN RAISE EXCEPTION 'injected history refusal'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER reject_history BEFORE INSERT ON supabase_migrations.schema_migrations
FOR EACH ROW EXECUTE FUNCTION public.reject_history();
""",
                    )
                with lock.open("w") as owner:
                    fcntl.flock(owner, fcntl.LOCK_EX)
                    with lock.open("w") as contender:
                        try:
                            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            pass
                        else:
                            raise RuntimeError(
                                "whole-window mutex admitted a second operator"
                            )
                    code, log = push(
                        cli,
                        container,
                        database,
                        target,
                        port,
                        stop_after_commit=label == "lost_ack",
                    )
                expect(counts(container, database) == wanted, label + " state")
                if label == "history_refusal":
                    expect(
                        code != 0 and "injected history refusal" in log,
                        "history failure was observed",
                    )
                    sql(
                        container,
                        database,
                        "DROP TRIGGER reject_history ON supabase_migrations.schema_migrations;",
                    )
                    with lock.open("w") as handle:
                        fcntl.flock(handle, fcntl.LOCK_EX)
                        retry_code, retry_log = push(
                            cli, container, database, target, port
                        )
                    expect(
                        retry_code != 0 and "duplicate key" in retry_log,
                        "serialized retry rejects committed unrecorded SQL",
                    )
                    expect(
                        counts(container, database) == (1, 0), "history gap persists"
                    )
                elif label == "lost_ack":
                    expect(code != 0, "client final acknowledgement was lost")
                    with lock.open("w") as handle:
                        fcntl.flock(handle, fcntl.LOCK_EX)
                        retry_code, retry_log = push(
                            cli, container, database, target, port
                        )
                    expect(
                        retry_code == 0 and "up to date" in retry_log,
                        "serialized duplicate attempt is a no-op",
                    )
                    expect(
                        counts(container, database) == (1, 1),
                        "lost-ack resume exact once",
                    )
                else:
                    expect(code != 0, label + " failed before ledger")
                print(f"{label}: CLI exit={code}, row/ledger={wanted}, PASS")

            # Smallest corrective placement: the history insert runs before
            # the source file's final COMMIT, preserving the file itself.
            corrected = "probe_corrected"
            setup_database(container, corrected)
            sql(
                container,
                corrected,
                f"""
CREATE FUNCTION public.reject_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.version = '{VERSION}' THEN RAISE EXCEPTION 'injected history refusal'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER reject_history BEFORE INSERT ON supabase_migrations.schema_migrations
FOR EACH ROW EXECUTE FUNCTION public.reject_history();
""",
            )
            corrected_sql = f"""
BEGIN;
INSERT INTO public.atomicity_probe VALUES (1);
INSERT INTO supabase_migrations.schema_migrations(version,name,statements)
VALUES ('{VERSION}','corrected',ARRAY[
  'BEGIN','INSERT INTO public.atomicity_probe VALUES (1)','COMMIT'
]::text[]);
COMMIT;
"""
            arguments = [
                "docker",
                "exec",
                "-i",
                container,
                "psql",
                "-U",
                "postgres",
                "-d",
                corrected,
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-Atq",
            ]
            refused = subprocess.run(
                arguments,
                input=corrected_sql,
                text=True,
                capture_output=True,
                check=False,
            )
            expect(refused.returncode != 0, "corrected history refusal was observed")
            expect(
                counts(container, corrected) == (0, 0),
                "corrected SQL and ledger rollback",
            )
            sql(
                container,
                corrected,
                "DROP TRIGGER reject_history ON supabase_migrations.schema_migrations;",
            )
            sql(container, corrected, corrected_sql)
            expect(
                counts(container, corrected) == (1, 1),
                "corrected SQL and ledger commit",
            )
            exact_history = sql(
                container,
                corrected,
                f"SELECT statements = ARRAY['BEGIN',"
                f"'INSERT INTO public.atomicity_probe VALUES (1)','COMMIT']::text[] "
                f"FROM supabase_migrations.schema_migrations WHERE version='{VERSION}';",
            )
            expect(
                exact_history == "t",
                "corrected history records parsed source statements",
            )
            print("history_before_inner_commit: rejected=(0, 0), accepted=(1, 1), PASS")
    finally:
        subprocess.run(["docker", "stop", container], capture_output=True, check=False)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--pg17"):
        raise SystemExit(
            "usage: probe_pinned_cli_explicit_transactions.py /path/to/supabase-go [--pg17]"
        )
    main(sys.argv[1], IMAGES["--pg17" if len(sys.argv) == 3 else "--pg15"])
