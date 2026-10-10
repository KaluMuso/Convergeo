"""Keep the historical nonsecret allowlists limited to their exact paths and values."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, cast

CONFIG = Path(__file__).resolve().parents[3] / ".gitleaks.toml"
CASES = (
    (
        "Google's published Linux signing-key fingerprint",
        "scripts/ci/check_hosted_chrome.sh",
        1,
        40,
    ),
    ("Coordinator source inventory", "scripts/ci/coordinator-gate-inputs.json", 8, 64),
)


def _allowlist(description: str) -> dict[str, Any]:
    blocks = tomllib.loads(CONFIG.read_text())["allowlists"]
    matching = [block for block in blocks if description in block["description"]]
    assert len(matching) == 1
    return cast("dict[str, Any]", matching[0])


def test_historical_false_positive_allowlists_are_exact() -> None:
    for description, path, count, width in CASES:
        block = _allowlist(description)
        assert block["condition"] == "AND"
        assert block["regexTarget"] == "secret"
        assert len(block["paths"]) == 1
        assert len(block["regexes"]) == count
        assert re.fullmatch(block["paths"][0], path)
        assert not re.fullmatch(block["paths"][0], f"other/{path}")
        assert not re.fullmatch(block["paths"][0], f"{path}.bak")

        values = [pattern[1:-1] for pattern in block["regexes"]]
        assert len(set(values)) == count
        for pattern, value in zip(block["regexes"], values, strict=True):
            assert pattern == f"^{value}$"
            assert re.fullmatch(rf"[0-9a-fA-F]{{{width}}}", value)
            assert re.fullmatch(pattern, value)
            changed = ("0" if value[0] != "0" else "1") + value[1:]
            assert not re.fullmatch(pattern, changed)
            assert not re.fullmatch(pattern, value + "0")
