"""Pytest collection-only plugin; no test implementation or SQL behavior is replaced."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from f2_real_stack_report import COLLECTION_SCHEMA, RELATED_MODULES


def pytest_collection_finish(session: Any) -> None:
    config = session.config
    output = Path(os.environ["F2_COLLECTION_OUTPUT"])
    if not config.option.collectonly or config.option.keyword or config.option.markexpr:
        raise ValueError("Related collection must be complete and unfiltered")
    if list(config.args) != list(RELATED_MODULES):
        raise ValueError("Unexpected related-suite collection arguments")
    if session.testsfailed:
        raise ValueError("Related collection failed")
    nodeids = [item.nodeid for item in session.items]
    if not nodeids or len(nodeids) != len(set(nodeids)):
        raise ValueError("Empty or duplicate related collection")
    if {n.split("::", 1)[0] for n in nodeids} != set(RELATED_MODULES):
        raise ValueError("Missing related module")
    data = {"schema": COLLECTION_SCHEMA, "modules": list(RELATED_MODULES), "nodeids": nodeids}
    temp = output.with_suffix(output.suffix + ".tmp")
    try:
        temp.write_text(json.dumps(data, indent=2) + "\n")
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
