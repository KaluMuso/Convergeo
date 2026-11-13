"""Regression tests for the Vercel Preview env-var selection/decrypt fix.

Covers the bug behind deploy-staging run #29's three Preview proof failures:
verify_project_env() interpreted Vercel's un-decrypted ciphertext envelope as
a hostname, and its row-selection did not deterministically prefer a
Git Branch=staging override over a generic Preview value.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "vercel_preview_env_verify.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("vercel_preview_env_verify", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_mod: Any = _module()

KEY = "NEXT_PUBLIC_API_BASE_URL"
STAGING_HOST = "api.staging.vergeo5.com"


def _row(
    value: str,
    *,
    git_branch: str | None = None,
    target: str = "preview",
    row_type: str = "encrypted",
    decrypted: bool | None = True,
    updated_at: int = 1,
    key: str = KEY,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "key": key,
        "value": value,
        "target": [target],
        "type": row_type,
        "updatedAt": updated_at,
    }
    if git_branch is not None:
        row["gitBranch"] = git_branch
    if decrypted is not None:
        row["decrypted"] = decrypted
    return row


def test_case_a_branch_specific_only_passes() -> None:
    rows = [_row(f"https://{STAGING_HOST}", git_branch="staging")]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "verified"
    assert result.host == STAGING_HOST


def test_case_b_branch_specific_wins_over_generic() -> None:
    rows = [
        _row("https://api.vergeo5.com", updated_at=1),  # generic Preview
        _row(f"https://{STAGING_HOST}", git_branch="staging", updated_at=2),
    ]
    # Generic row would be forbidden (production host) if ever selected —
    # proves the branch-specific row is what actually gets picked, not luck.
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "verified"
    assert result.host == STAGING_HOST


def test_case_b_branch_specific_wins_regardless_of_row_order() -> None:
    rows = [
        _row(f"https://{STAGING_HOST}", git_branch="staging", updated_at=2),
        _row("https://generic-preview.vergeo5.com", updated_at=1),
    ]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "verified"
    assert result.host == STAGING_HOST


def test_case_c_generic_only_fails_closed_when_override_required() -> None:
    rows = [_row(f"https://{STAGING_HOST}")]  # correct host, but no gitBranch
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "missing_branch_override"


def test_case_c_generic_only_passes_when_override_not_required() -> None:
    rows = [_row(f"https://{STAGING_HOST}")]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST, require_branch_override=False)
    assert result.verdict == "verified"
    assert result.host == STAGING_HOST


def test_case_d_ciphertext_not_interpreted_as_hostname() -> None:
    ciphertext = "eyJ2IjoiMSIsImMiOiJhYmMxMjNkZWYidmVyeWxvbmdjaXBoZXJ0ZXh0Ymxvbndpbm5vZG90cyJ9"
    rows = [_row(ciphertext, git_branch="staging", decrypted=False)]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "ciphertext"
    assert result.host is None


def test_case_d_ciphertext_shape_guarded_even_without_decrypted_flag() -> None:
    # Defense in depth: a dot-free, unusually long blob is refused as a host
    # even if type/decrypted metadata is ever absent from the API response.
    blob = "eyJ2IjoiMSIsImMiOiJhYmMxMjNkZWYidmVyeWxvbmdjaXBoZXJ0ZXh0Ymxvbndpbm5vZG90cyJ9"
    row = {"key": KEY, "value": blob, "target": ["preview"], "gitBranch": "staging"}
    result = verify_mod.verify([row], KEY, "staging", STAGING_HOST)
    assert result.verdict == "ciphertext"
    assert result.host is None


def test_case_e_branch_specific_pointing_at_production_fails() -> None:
    rows = [_row("https://api.vergeo5.com", git_branch="staging")]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "forbidden"


def test_case_f_branch_specific_pointing_at_localhost_fails() -> None:
    rows = [_row("http://localhost:3000", git_branch="staging")]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "forbidden"


def test_missing_entirely() -> None:
    result = verify_mod.verify([], KEY, "staging", STAGING_HOST)
    assert result.verdict == "missing"


def test_host_mismatch_does_not_leak_host_via_verdict_string() -> None:
    rows = [_row("https://wrong-host.example.com", git_branch="staging")]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "host_mismatch"
    # host is available on the dataclass for callers that need it (tests),
    # but the CLI (main()) only ever prints result.verdict — see
    # test_cli_never_prints_raw_value below.
    assert result.host == "wrong-host.example.com"


def test_different_branch_row_is_not_a_candidate() -> None:
    rows = [
        _row("https://api-preview-otherbranch.vergeo5.com", git_branch="feature-x"),
    ]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "missing"


def test_wrong_target_row_is_ignored() -> None:
    rows = [_row(f"https://{STAGING_HOST}", git_branch="staging", target="production")]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "missing"


def test_plain_type_ignores_decrypted_flag() -> None:
    rows = [
        _row(
            f"https://{STAGING_HOST}",
            git_branch="staging",
            row_type="plain",
            decrypted=None,
        )
    ]
    result = verify_mod.verify(rows, KEY, "staging", STAGING_HOST)
    assert result.verdict == "verified"


def test_cli_never_prints_raw_value(tmp_path: Path, capsys: Any) -> None:
    import json

    ciphertext = "eyJ2IjoiMSIsImMiOiJzdXBlcnNlY3JldGxvbmdjaXBoZXJ0ZXh0d2l0aG5vZG90cyJ9"
    env_json_file = tmp_path / "env.json"
    env_json_file.write_text(
        json.dumps(
            [
                {
                    "key": KEY,
                    "value": ciphertext,
                    "target": ["preview"],
                    "gitBranch": "staging",
                    "type": "encrypted",
                    "decrypted": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    rc = verify_mod.main(
        [
            "--key",
            KEY,
            "--git-branch",
            "staging",
            "--expected-host",
            STAGING_HOST,
            "--env-json-file",
            str(env_json_file),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "ciphertext"
    assert ciphertext not in out


def test_cli_host_mismatch_does_not_print_host(tmp_path: Path, capsys: Any) -> None:
    import json

    env_json_file = tmp_path / "env.json"
    env_json_file.write_text(
        json.dumps(
            [
                {
                    "key": KEY,
                    "value": "https://totally-wrong-host.example.com",
                    "target": ["preview"],
                    "gitBranch": "staging",
                    "type": "plain",
                }
            ]
        ),
        encoding="utf-8",
    )
    rc = verify_mod.main(
        [
            "--key",
            KEY,
            "--git-branch",
            "staging",
            "--expected-host",
            STAGING_HOST,
            "--env-json-file",
            str(env_json_file),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "host_mismatch"
    assert "totally-wrong-host" not in out
