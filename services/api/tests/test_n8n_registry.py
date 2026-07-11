"""Completeness check: every infra/n8n/*.json is documented in the registry (M13-P11)."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_N8N_DIR = _REPO_ROOT / "infra" / "n8n"
_REGISTRY_DOC = _REPO_ROOT / "docs" / "ops" / "n8n-workflows.md"


def _workflow_files() -> list[Path]:
    return sorted(_N8N_DIR.glob("*.json"))


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
