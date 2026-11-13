"""Regenerate app/data/web_push_messages.json from packages/i18n/messages.

The API image only contains services/api, so the strings the Web Push sender
renders server-side (``notifications.title`` + ``notifications.inApp.*``) are
snapshotted here. ``tests/test_web_push.py`` fails when the snapshot drifts from
the canonical catalog; run ``uv run python scripts/sync_web_push_messages.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
SOURCE_DIR = REPO_ROOT / "packages/i18n/messages"
TARGET = API_ROOT / "app/data/web_push_messages.json"
LOCALES = ("en", "bem", "nya", "fr", "zh")


def build_snapshot(source_dir: Path = SOURCE_DIR) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for locale in LOCALES:
        data = json.loads((source_dir / locale / "notifications.json").read_text("utf-8"))
        snapshot[locale] = {"title": data.get("title"), "inApp": data.get("inApp", {})}
    return snapshot


def render(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    TARGET.write_text(render(build_snapshot()), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
