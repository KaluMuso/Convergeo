from __future__ import annotations

import re
from pathlib import Path

SERVICE_ROLE_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+app\.supabase_client\s+import|import\s+app\.supabase_client\b)",
    re.MULTILINE,
)

ALLOWED_IMPORTER_PATHS = frozenset(
    {
        "app/deps.py",
        "app/supabase_client.py",
    }
)

ALLOWED_IMPORTER_PREFIXES = (
    "app/core/",
)


def _is_allowed_importer(relative_path: str) -> bool:
    if relative_path in ALLOWED_IMPORTER_PATHS:
        return True
    return any(relative_path.startswith(prefix) for prefix in ALLOWED_IMPORTER_PREFIXES)


def test_service_role_imports_confined_to_allowlist() -> None:
    api_root = Path(__file__).resolve().parents[1]
    app_root = api_root / "app"
    violations: list[str] = []

    for py_file in sorted(app_root.rglob("*.py")):
        relative_path = py_file.relative_to(api_root).as_posix()
        if relative_path == "app/supabase_client.py":
            continue

        content = py_file.read_text(encoding="utf-8")
        if not SERVICE_ROLE_IMPORT_PATTERN.search(content):
            continue

        if not _is_allowed_importer(relative_path):
            violations.append(relative_path)

    assert violations == [], (
        "Service-role client imports must stay greppable to approved modules only. "
        f"Unexpected importers: {violations}"
    )
