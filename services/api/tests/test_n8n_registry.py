"""Completeness check: every infra/n8n/*.json is documented in the registry (M13-P11),
and every internal API endpoint a workflow calls is documented too (drift guard, 2026-07)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_N8N_DIR = _REPO_ROOT / "infra" / "n8n"
_REGISTRY_DOC = _REPO_ROOT / "docs" / "ops" / "n8n-workflows.md"

# Internal API paths a workflow POSTs to, e.g. /internal/reconciliation/poll-tick,
# whether the url is `{{$env.API_URL}}/internal/...` or a literal host.
_INTERNAL_PATH_RE = re.compile(r"/internal/[A-Za-z0-9_\-/]+")


def _workflow_files() -> list[Path]:
    return sorted(_N8N_DIR.glob("*.json"))


def _internal_endpoint_segments(workflow: Path) -> set[str]:
    """Last path segment of every /internal/... endpoint the workflow calls.

    The segment (e.g. ``poll-tick``, ``auto-confirm``) is distinctive and tolerates the
    registry's brace shorthand (``/internal/order-jobs/{auto-confirm,auto-release}``),
    which documents each segment without the fully-expanded path.
    """
    data = json.loads(workflow.read_text(encoding="utf-8"))
    segments: set[str] = set()
    for node in data.get("nodes", []):
        params = node.get("parameters") or {}
        url = params.get("url")
        if isinstance(url, str):
            for path in _INTERNAL_PATH_RE.findall(url):
                segments.add(path.rstrip("/").rsplit("/", 1)[-1])
    return segments


def test_n8n_dir_and_registry_exist() -> None:
    assert _N8N_DIR.is_dir(), f"missing n8n workflow dir: {_N8N_DIR}"
    assert _REGISTRY_DOC.is_file(), f"missing registry doc: {_REGISTRY_DOC}"
    assert _workflow_files(), "expected at least one n8n workflow json"


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_every_workflow_is_registered(workflow: Path) -> None:
    registry = _REGISTRY_DOC.read_text(encoding="utf-8")
    assert workflow.name in registry, (
        f"{workflow.name} is not documented in docs/ops/n8n-workflows.md — "
        "add its row to the Registry table"
    )


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_every_internal_endpoint_is_documented(workflow: Path) -> None:
    """The registry's Endpoint column must not silently drift from the workflow JSON:
    every /internal/... path a workflow POSTs to must appear in n8n-workflows.md."""
    registry = _REGISTRY_DOC.read_text(encoding="utf-8")
    missing = sorted(
        segment for segment in _internal_endpoint_segments(workflow) if segment not in registry
    )
    assert not missing, (
        f"{workflow.name} calls internal endpoint(s) absent from "
        f"docs/ops/n8n-workflows.md: {missing} — update its Endpoint column"
    )
