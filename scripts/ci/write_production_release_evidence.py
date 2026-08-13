#!/usr/bin/env python3
"""Write production frontend release evidence JSON artifact."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    if len(sys.argv) not in {6, 7}:
        print(
            "usage: write_production_release_evidence.py "
            "<out-path> <candidate-sha> <run-id> <evidence-path> <verdict> [emergency_mode]",
            file=sys.stderr,
        )
        return 2

    out_path = Path(sys.argv[1])
    emergency_mode = sys.argv[6] if len(sys.argv) == 7 else "normal"
    payload = {
        "gate": "RELCTRL-01",
        "verdict": sys.argv[5],
        "candidate_frontend_sha": sys.argv[2],
        "production_branch": "production",
        "promoted_at": datetime.now(UTC).isoformat(),
        "workflow_run_id": sys.argv[3],
        "release_evidence_path": sys.argv[4],
        "emergency_mode": emergency_mode,
        "note": (
            "Frontend-only promotion; API/DB parity attested via release contract "
            "and capture-production-db-evidence artifact"
        ),
    }
    if emergency_mode == "degraded":
        payload["degraded_proof"] = (
            "Post-promotion Vercel wait and/or verify_live.sh skipped under "
            "emergency_confirm=I_ACCEPT_DEGRADED_PRODUCTION_EVIDENCE"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
