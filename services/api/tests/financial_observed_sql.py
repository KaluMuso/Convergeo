"""Isolated-fixture diagnostics; never change production error disclosure or SQL results."""
from __future__ import annotations

import json
import os
from collections.abc import Callable

import pytest
from app.services.db import SqlResult, run_sql_script


def capture_native_sql(request: pytest.FixtureRequest, *, label: str) -> Callable[[str], SqlResult]:
    def execute(script: str) -> SqlResult:
        result = run_sql_script(script)
        if "LANE_D_POSTGREST_URL" in os.environ and (
            "$order_authority$" in script or (label == "rfq_accept" and not result.ok)
        ):
            statuses = {"placed", "confirmed", "processing", "ready", "shipped", "delivered",
                        "completed", "cancelled"}
            # The production projection includes the order's locked id/status and UPDATE
            # RETURNING status. Command tags are not data in the native adapter.
            evidence = {
                "ok": result.ok, "rows": result.rows, "error": result.error,
                "locked_rows": [r for r in result.rows if "|" in r
                                and r.rsplit("|", 1)[-1] in statuses],
                "returned_status_rows": [r for r in result.rows if r in statuses],
                "affected_rows": sum(r in statuses for r in result.rows),
            }
            text = json.dumps(evidence, sort_keys=True)
            request.node.user_properties.append((label + "_sql_result", text))
            print(label + "_sql_result=" + text)
        return result
    return execute
