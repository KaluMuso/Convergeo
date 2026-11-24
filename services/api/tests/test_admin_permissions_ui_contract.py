"""The admin app rejects any permission it does not know (fail-closed).

So every permission the API can grant must also be in the admin UI allowlist,
otherwise a new API permission locks every admin out of the console.
"""

import re
from pathlib import Path

from app.core.auth import ADMIN_PERMISSIONS

ROLES_API = Path(__file__).resolve().parents[3] / "apps/admin/lib/roles-api.ts"


def test_admin_ui_allowlist_covers_every_api_permission() -> None:
    source = ROLES_API.read_text(encoding="utf-8")
    block = source.split("const PERMISSIONS = new Set([", 1)[1].split("]);", 1)[0]
    ui_permissions = set(re.findall(r'"([a-z_]+\.[a-z_]+)"', block))
    missing = sorted(set(ADMIN_PERMISSIONS) - ui_permissions)
    assert not missing, f"add to apps/admin/lib/roles-api.ts PERMISSIONS: {missing}"
