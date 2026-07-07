from __future__ import annotations

import json
from pathlib import Path

from app.main import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def export_openapi(output_path: Path = DEFAULT_OUTPUT) -> Path:
    app = create_app()
    schema = app.openapi()
    output_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    path = export_openapi()
    print(f"OpenAPI schema written to {path}")
