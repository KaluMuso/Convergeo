"""Fail-closed source and lexer controls for five explicit-transaction migrations."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from explicit_transaction_boundary import (
    BOUND_FILES,
    BoundaryError,
    parse_bound_file,
    verify_disposable_prefix,
)
from rehearse_explicit_transaction_profile import (
    CONTAINER,
    IMAGE,
    RehearsalError,
    StageTracker,
    WindowState,
    check_cli_reference,
    checked,
    failure_marker,
    mark_owned,
    owned_window,
    run,
    source_inventory,
    sql,
    target_container,
    visible_prefix,
)


class BoundaryTests(unittest.TestCase):
    def parse_fixture(self, raw: bytes):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            filename = "20261006000000_fixture.sql"
            (path / filename).write_bytes(raw)
            with patch.dict(BOUND_FILES, {filename: hashlib.sha256(raw).hexdigest()}):
                return parse_bound_file(filename, migrations=path)

    def test_all_five_original_files_have_exact_outer_boundary(self) -> None:
        expected_counts = (27, 14, 9, 13, 3)
        for (filename, _), count in zip(
            BOUND_FILES.items(), expected_counts, strict=True
        ):
            with self.subTest(filename=filename):
                boundary = parse_bound_file(filename)
                self.assertEqual(len(boundary.statements), count)
                rendered = boundary.with_disposable_history_before_commit()
                insertion = (
                    b"\n" + boundary.disposable_history_insert().encode() + b"\n"
                )
                self.assertEqual(
                    rendered,
                    boundary.raw[: boundary.commit_offset]
                    + insertion
                    + boundary.raw[boundary.commit_offset :],
                )
                self.assertEqual(rendered.replace(insertion, b"", 1), boundary.raw)
                encoded = re.findall(rb"decode\('([0-9a-f]+)','hex'\)", insertion)
                self.assertEqual(
                    tuple(bytes.fromhex(item.decode()).decode() for item in encoded),
                    boundary.statements,
                )

    def test_comments_quotes_and_dollar_body_do_not_move_commit(self) -> None:
        raw = b"""-- fake COMMIT; and BEGIN;
BEGIN;
/* outer; /* nested COMMIT; */ still comment */
DO $body$ BEGIN; RAISE NOTICE 'COMMIT;'; END $body$;
SELECT 'it''s; fine'::text, 'COMMIT;'::text;
COMMIT;
-- trailing COMMIT; comment
"""
        boundary = self.parse_fixture(raw)
        self.assertEqual(len(boundary.statements), 4)
        self.assertEqual(raw[boundary.commit_offset :].split(b";", 1)[0], b"COMMIT")

    def test_refuses_changed_or_unreviewed_source(self) -> None:
        filename = next(iter(BOUND_FILES))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / filename).write_bytes(b"BEGIN; SELECT 1; COMMIT;")
            with self.assertRaises(BoundaryError):
                parse_bound_file(filename, migrations=path)
        with self.assertRaises(BoundaryError):
            parse_bound_file("../" + filename)

    def test_refuses_unsupported_or_ambiguous_sql(self) -> None:
        cases = (
            b"BEGIN; SELECT 1; COMMIT; COMMIT;",
            b"BEGIN; SELECT 1; ROLLBACK; COMMIT;",
            b"BEGIN; CREATE INDEX CONCURRENTLY x ON t(c); COMMIT;",
            b"BEGIN; COPY t FROM STDIN; COMMIT;",
            b"BEGIN; \\gexec\nCOMMIT;",
            b"BEGIN; SELECT 'unterminated; COMMIT;",
            b"BEGIN; DO $tag$ SELECT 1; COMMIT;",
            b"BEGIN; /* unterminated COMMIT;",
            b"BEGIN; SELECT E'back\\slash'; COMMIT;",
            b"BEGIN; SELECT 1; COMMIT",
        )
        for raw in cases:
            with self.subTest(case=raw[:40]), self.assertRaises(BoundaryError):
                self.parse_fixture(raw)

    def test_resume_requires_exact_six_column_prefix(self) -> None:
        rows = [
            parse_bound_file(filename).disposable_history_row()
            for filename in BOUND_FILES
        ]
        for count in range(len(rows) + 1):
            with self.subTest(prefix=count):
                self.assertEqual(verify_disposable_prefix(rows[:count]), count)
        tampered = list(rows[0])
        tampered[2] = ("BEGIN", "COMMIT")
        invalid = (
            [rows[1]],  # Gap or out-of-order history.
            [tuple(tampered)],  # The same version with different SQL.
            [rows[0], rows[0]],  # Duplicate history.
            [(*rows[0][:3], "unexpected", *rows[0][4:])],
            [*rows, rows[-1]],
        )
        for case in invalid:
            with self.subTest(case=str(case)[:40]), self.assertRaises(BoundaryError):
                verify_disposable_prefix(case)

    def test_missing_or_malformed_profile_is_source_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            with self.assertRaises(RehearsalError) as missing_profile:
                source_inventory(workdir)
            self.assertEqual(missing_profile.exception.code, "SOURCE_MISMATCH")
            (workdir / "supabase").mkdir()
            (workdir / "supabase/config.toml").write_text("bad[", encoding="utf-8")
            with self.assertRaises(RehearsalError) as malformed_profile:
                source_inventory(workdir)
            self.assertEqual(malformed_profile.exception.code, "SOURCE_MISMATCH")

    def test_disposable_prefix_copy_is_restored_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            subprocess.run(
                ["bash", "scripts/ci/prepare-typegen-workdir.sh", str(workdir)],
                check=True,
                capture_output=True,
            )
            files, first = source_inventory(workdir)
            self.assertEqual((len(files), first), (139, 131))
            with self.assertRaisesRegex(RuntimeError, "fault"):
                with visible_prefix(files, first - 1, workdir):
                    self.assertEqual(
                        len(list((workdir / "supabase/migrations").glob("*.sql"))), 131
                    )
                    raise RuntimeError("fault")
            self.assertEqual(
                len(list((workdir / "supabase/migrations").glob("*.sql"))), 139
            )
            copied = workdir / "supabase/migrations" / next(iter(BOUND_FILES))
            copied.write_bytes(copied.read_bytes() + b"\n")
            with self.assertRaises(RehearsalError) as changed_copy:
                source_inventory(workdir)
            self.assertEqual(changed_copy.exception.code, "SOURCE_MISMATCH")

    def test_fault_must_reach_fixture_history_trigger(self) -> None:
        wrong = subprocess.CompletedProcess([], 3, b"", b"earlier SQL error")
        right = subprocess.CompletedProcess([], 3, b"", b"disposable history refusal")
        with patch(
            "rehearse_explicit_transaction_profile.subprocess.run", return_value=wrong
        ):
            with self.assertRaises(RehearsalError):
                sql("fixture", "BEGIN; COMMIT;", expected_failure=True)
        with patch(
            "rehearse_explicit_transaction_profile.subprocess.run", return_value=right
        ):
            sql("fixture", "BEGIN; COMMIT;", expected_failure=True)

    def test_cli_reference_rejects_statement_serialization_difference(self) -> None:
        files = sorted(
            (Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql")
        )
        rows = [
            [
                path.stem.split("_", 1)[0],
                path.stem.split("_", 1)[1],
                [],
                None,
                None,
                None,
            ]
            for path in files
        ]
        for filename in BOUND_FILES:
            boundary = parse_bound_file(filename)
            row = next(item for item in rows if item[0] == boundary.version)
            row[2] = list(boundary.statements)
        with (
            patch("rehearse_explicit_transaction_profile.ledger", return_value=rows),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(len(check_cli_reference("fixture", files, 131)), 131)
        row = next(
            item
            for item in rows
            if item[0] == parse_bound_file(next(iter(BOUND_FILES))).version
        )
        row[2] = ["BEGIN", "COMMIT"]
        with patch("rehearse_explicit_transaction_profile.ledger", return_value=rows):
            with self.assertRaises(RehearsalError):
                check_cli_reference("fixture", files, 131)
        row[2] = list(parse_bound_file(next(iter(BOUND_FILES))).statements)
        row[3] = "unexpected creator"
        with patch("rehearse_explicit_transaction_profile.ledger", return_value=rows):
            with self.assertRaises(RehearsalError):
                check_cli_reference("fixture", files, 131)

    def test_failure_cleanup_requires_stack_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            files = [workdir / f"{index}.sql" for index in range(139)]
            with (
                patch(
                    "rehearse_explicit_transaction_profile.LOCK",
                    workdir / "window.lock",
                ),
                patch(
                    "rehearse_explicit_transaction_profile.checked",
                    return_value=b"preexisting",
                ),
                patch("rehearse_explicit_transaction_profile.cli") as cli,
            ):
                with self.assertRaises(RehearsalError):
                    with owned_window(workdir, files):
                        self.fail("pre-existing stack was admitted")
                cli.assert_not_called()
                self.assertFalse((workdir / ".owned-typegen-stack").exists())
            with (
                patch(
                    "rehearse_explicit_transaction_profile.LOCK",
                    workdir / "window.lock",
                ),
                patch(
                    "rehearse_explicit_transaction_profile.checked", return_value=b""
                ),
                patch(
                    "rehearse_explicit_transaction_profile.source_inventory",
                    return_value=(files, 131),
                ),
                patch(
                    "rehearse_explicit_transaction_profile.target_container",
                    return_value="abcdef123456",
                ),
                patch(
                    "rehearse_explicit_transaction_profile.ledger",
                    return_value=[[]] * 139,
                ),
                patch("rehearse_explicit_transaction_profile.cli") as cli,
                redirect_stdout(io.StringIO()),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    with owned_window(workdir, files) as state:
                        mark_owned(workdir, state, "abcdef123456")
                        raise RuntimeError("injected")
                cli.assert_called_once_with(workdir, "reset", "--no-seed")
            self.assertEqual(
                (workdir / ".owned-typegen-stack").read_text(), "abcdef123456\n"
            )

    def test_failure_marker_only_uses_allowlisted_stage_and_code(self) -> None:
        tracker = StageTracker()
        with redirect_stderr(io.StringIO()) as output:
            tracker.enter("container_identity")
            marker = failure_marker(
                tracker,
                RehearsalError("secret SQL and database URL", code="IMAGE_MISMATCH"),
            )
        self.assertEqual(output.getvalue(), "proof_stage|container_identity|BEGIN\n")
        self.assertEqual(
            marker,
            "error: bounded disposable proof failed: "
            "stage=container_identity code=IMAGE_MISMATCH",
        )
        self.assertNotIn("secret", marker + output.getvalue())
        with self.assertRaises(ValueError):
            tracker.enter("hosted_db_url")
        with self.assertRaises(ValueError):
            RehearsalError("secret", code="SECRET")
        tracker.current = "private stage"
        altered = RehearsalError("private message")
        altered.code = "private code"
        self.assertEqual(
            failure_marker(tracker, altered),
            "error: bounded disposable proof failed: "
            "stage=entry code=UNEXPECTED_EXCEPTION",
        )

    def test_source_failure_reports_first_stage_without_exception_text(self) -> None:
        tracker = StageTracker()
        with (
            patch(
                "rehearse_explicit_transaction_profile.source_inventory",
                side_effect=RehearsalError("private source", code="SOURCE_MISMATCH"),
            ),
            redirect_stderr(io.StringIO()) as output,
            self.assertRaises(RehearsalError) as caught,
        ):
            run(Path("/tmp/disposable"), tracker)
        self.assertEqual(caught.exception.code, "SOURCE_MISMATCH")
        self.assertEqual(output.getvalue(), "proof_stage|source_inventory|BEGIN\n")
        self.assertNotIn("private", failure_marker(tracker, caught.exception))

    def test_container_guard_distinguishes_image_and_missing_container(self) -> None:
        container_id = "abcdef123456"
        details = {
            "Name": f"/{CONTAINER}",
            "Config": {"Image": "unreviewed-image"},
            "State": {"Running": True},
            "NetworkSettings": {
                "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54322"}]}
            },
        }
        with patch("rehearse_explicit_transaction_profile.checked", return_value=b""):
            with self.assertRaises(RehearsalError) as missing:
                target_container()
        self.assertEqual(missing.exception.code, "CONTAINER_MISSING")
        with patch(
            "rehearse_explicit_transaction_profile.checked",
            side_effect=[container_id.encode(), json.dumps(details).encode()],
        ):
            with self.assertRaises(RehearsalError) as wrong_image:
                target_container()
        self.assertEqual(wrong_image.exception.code, "IMAGE_MISMATCH")
        details["Config"]["Image"] = IMAGE
        with (
            patch(
                "rehearse_explicit_transaction_profile.checked",
                side_effect=[container_id.encode(), json.dumps(details).encode()],
            ),
            patch("rehearse_explicit_transaction_profile.sql", return_value=b"150000"),
        ):
            with self.assertRaises(RehearsalError) as wrong_version:
                target_container()
        self.assertEqual(wrong_version.exception.code, "VERSION_MISMATCH")

    def test_failed_command_does_not_expose_subprocess_stderr(self) -> None:
        result = subprocess.CompletedProcess([], 17, b"", b"private command stderr")
        with patch(
            "rehearse_explicit_transaction_profile.subprocess.run", return_value=result
        ):
            with self.assertRaises(RehearsalError) as caught:
                checked(["supabase", "--version"])
        self.assertEqual(caught.exception.code, "COMMAND_FAILED")
        self.assertNotIn("private", failure_marker(StageTracker(), caught.exception))
        for failure in (
            OSError("private executable path"),
            subprocess.TimeoutExpired(["private-command"], 1),
        ):
            with (
                self.subTest(failure=type(failure).__name__),
                patch(
                    "rehearse_explicit_transaction_profile.subprocess.run",
                    side_effect=failure,
                ),
                self.assertRaises(RehearsalError) as unavailable,
            ):
                checked(["supabase", "--version"])
            self.assertEqual(unavailable.exception.code, "COMMAND_UNAVAILABLE")
            self.assertNotIn(
                "private", failure_marker(StageTracker(), unavailable.exception)
            )

    def test_pre_start_guards_keep_specific_stage_and_code(self) -> None:
        source_files = sorted(
            (Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql")
        )
        cases = (
            ("checkout_identity", "SOURCE_MISMATCH"),
            ("suffix_order", "SOURCE_MISMATCH"),
            ("cli_version", "CLI_VERSION_MISMATCH"),
            ("scratch_directory", "WORKDIR_UNAVAILABLE"),
            ("stack_ownership", "CONTAINER_MISMATCH"),
            ("prefix_copy", "WORKDIR_UNAVAILABLE"),
        )
        for failed_stage, expected_code in cases:
            with (
                self.subTest(stage=failed_stage),
                tempfile.TemporaryDirectory() as directory,
            ):
                files = source_files.copy()
                if failed_stage == "suffix_order":
                    files[-2] = files[0]

                def fake_checked(args, **_kwargs):
                    if args[0] == "supabase":
                        return b"2.0.0" if failed_stage == "cli_version" else b"2.109.1"
                    if failed_stage == "checkout_identity" and args[-1] == "HEAD":
                        return b"invalid-source"
                    return b"a" * 40

                tracker = StageTracker()
                with (
                    patch.dict(os.environ, {"QUALIFICATION_SHA": "a" * 40}),
                    patch(
                        "rehearse_explicit_transaction_profile.source_inventory",
                        return_value=(files, 131),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.checked",
                        side_effect=fake_checked,
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.TemporaryDirectory",
                        side_effect=(
                            OSError("private scratch path")
                            if failed_stage == "scratch_directory"
                            else None
                        ),
                        return_value=nullcontext(directory),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.owned_window",
                        side_effect=(
                            RehearsalError(
                                "private preexisting container",
                                code="CONTAINER_MISMATCH",
                            )
                            if failed_stage == "stack_ownership"
                            else None
                        ),
                        return_value=nullcontext(WindowState()),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.visible_prefix",
                        side_effect=(
                            OSError("private migration path")
                            if failed_stage == "prefix_copy"
                            else None
                        ),
                        return_value=nullcontext(),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.cli",
                        side_effect=RehearsalError(
                            "private CLI output", code="COMMAND_FAILED"
                        ),
                    ),
                    redirect_stderr(io.StringIO()) as output,
                    self.assertRaises(Exception) as caught,
                ):
                    run(Path(directory), tracker)
                self.assertEqual(tracker.current, failed_stage)
                marker = failure_marker(tracker, caught.exception)
                self.assertEqual(
                    marker,
                    "error: bounded disposable proof failed: "
                    f"stage={failed_stage} code={expected_code}",
                )
                self.assertNotIn("private", marker + output.getvalue())

    def test_first_runtime_boundary_identifies_start_or_container_guard(self) -> None:
        files = sorted(
            (Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql")
        )

        def fake_checked(args, **_kwargs):
            if args[0] == "supabase":
                return b"2.109.1"
            return b"a" * 40

        for failure, expected_stage in (
            ("start", "cli_start"),
            ("container", "container_identity"),
        ):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                tracker = StageTracker()
                with (
                    patch.dict(os.environ, {"QUALIFICATION_SHA": "a" * 40}),
                    patch(
                        "rehearse_explicit_transaction_profile.source_inventory",
                        return_value=(files, 131),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.checked",
                        side_effect=fake_checked,
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.owned_window",
                        return_value=nullcontext(WindowState()),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.visible_prefix",
                        return_value=nullcontext(),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.cli",
                        side_effect=(
                            RehearsalError("private CLI stderr", code="COMMAND_FAILED")
                            if failure == "start"
                            else None
                        ),
                    ),
                    patch(
                        "rehearse_explicit_transaction_profile.target_container",
                        side_effect=RehearsalError(
                            "private Docker inspect", code="IMAGE_MISMATCH"
                        ),
                    ),
                    redirect_stderr(io.StringIO()) as output,
                    self.assertRaises(RehearsalError) as caught,
                ):
                    run(Path(directory), tracker)
                self.assertEqual(tracker.current, expected_stage)
                marker = failure_marker(tracker, caught.exception)
                self.assertIn(f"stage={expected_stage}", marker)
                self.assertNotIn("private", marker + output.getvalue())


if __name__ == "__main__":
    unittest.main()
