"""T48: admin read surfaces resolve ids to names/emails, search and page (DB-free).

Reachability for every identity stays in tests/test_admin_role_route_matrix.py; these
tests pin the read-only enrichment and pagination contracts.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.admin_people import clean_search_term, people_by_ids, search_people
from app.supabase_client import get_supabase_service_client
from fastapi.testclient import TestClient

USER = "00000000-0000-0000-0000-0000000000a1"
TARGET = "00000000-0000-0000-0000-0000000000b2"
OTHER = "00000000-0000-0000-0000-0000000000c3"
VENDOR = "00000000-0000-0000-0000-0000000000d4"


class Query:
    """Chainable fake: applies eq/in_/ilike/range on canned rows and records every call."""

    def __init__(self, fake: Fake, table: str) -> None:
        self.fake = fake
        self.table = table
        self.rows = [dict(row) for row in fake.rows.get(table, [])]
        self.count_requested = False
        self.window: tuple[int, int] | None = None

    def _record(self, method: str, *args: Any) -> Query:
        self.fake.calls.append((self.table, method, args))
        return self

    def select(self, columns: str, *, count: str | None = None) -> Query:
        self.count_requested = count == "exact"
        return self._record("select", columns)

    def eq(self, column: str, value: Any) -> Query:
        self.rows = [row for row in self.rows if row.get(column) == value]
        return self._record("eq", column, value)

    def in_(self, column: str, values: list[Any]) -> Query:
        self.rows = [row for row in self.rows if row.get(column) in set(values)]
        return self._record("in_", column, list(values))

    def ilike(self, column: str, pattern: str) -> Query:
        needle = pattern.strip("%").lower()
        self.rows = [row for row in self.rows if needle in str(row.get(column) or "").lower()]
        return self._record("ilike", column, pattern)

    def or_(self, expression: str) -> Query:
        return self._record("or_", expression)

    def order(self, column: str, *, desc: bool = False) -> Query:
        return self._record("order", column, desc)

    def limit(self, count: int) -> Query:
        self.rows = self.rows[:count]
        return self._record("limit", count)

    def range(self, start: int, end: int) -> Query:
        self.window = (start, end)
        return self._record("range", start, end)

    def like(self, *args: Any) -> Query:
        return self._record("like", *args)

    def gte(self, *args: Any) -> Query:
        return self._record("gte", *args)

    def lte(self, *args: Any) -> Query:
        return self._record("lte", *args)

    def lt(self, *args: Any) -> Query:
        return self._record("lt", *args)

    def execute(self) -> SimpleNamespace:
        total = len(self.rows)
        rows = self.rows
        if self.window is not None:
            rows = rows[self.window[0] : self.window[1] + 1]
        return SimpleNamespace(data=rows, count=total if self.count_requested else None)


class Fake:
    def __init__(
        self,
        rows: dict[str, list[dict[str, Any]]] | None = None,
        auth_users: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows = rows or {}
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.client = self
        emails = {user["id"]: user.get("email") for user in auth_users or []}
        users = auth_users or []

        def request(method: str, path: str, *, query: Any = None) -> Any:
            assert (method, path) == ("GET", "admin/users")
            term = str(query.get("filter", "")).lower()
            matches = [u for u in users if term in str(u.get("email", "")).lower()]
            return SimpleNamespace(json=lambda: {"users": matches})

        def list_users(page: int | None = None, per_page: int | None = None) -> list[Any]:
            per = per_page or 1000
            start = ((page or 1) - 1) * per
            chunk = users[start : start + per]
            return [
                SimpleNamespace(id=u["id"], email=u.get("email"))
                for u in chunk
                if isinstance(u.get("id"), str)
            ]

        self.auth = SimpleNamespace(
            admin=SimpleNamespace(
                get_user_by_id=lambda uid: SimpleNamespace(
                    user=SimpleNamespace(email=emails.get(uid))
                ),
                list_users=list_users,
                _request=request,
            )
        )

    def table(self, name: str) -> Query:
        return Query(self, name)

    def calls_for(self, table: str, method: str) -> list[tuple[Any, ...]]:
        return [args for t, m, args in self.calls if t == table and m == method]


def _client(
    monkeypatch: pytest.MonkeyPatch,
    fake: Fake,
    roles: frozenset[str] = frozenset({"superadmin"}),
) -> TestClient:
    fake.rows.setdefault("admin_roles", [])
    app = create_app()
    user = CurrentUser(id=USER, roles=roles, token="t")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_supabase_client] = lambda: fake
    app.dependency_overrides[get_supabase_service_client] = lambda: fake
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: fake)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: fake)
    return TestClient(app, raise_server_exceptions=False)


PEOPLE: dict[str, list[dict[str, Any]]] = {
    "profiles": [
        {"id": TARGET, "display_name": "Chanda Mwale"},
        {"id": USER, "display_name": "Founder King"},
        {"id": OTHER, "display_name": None},
    ]
}
AUTH_USERS = [
    {"id": TARGET, "email": "chanda@example.test"},
    {"id": USER, "email": "king@example.test"},
    {"id": OTHER, "email": "ops-only@example.test"},
]


# ---------------------------------------------------------------------------
# admin_people helpers
# ---------------------------------------------------------------------------


def test_clean_search_term_strips_filter_syntax_and_wildcards() -> None:
    assert clean_search_term("  chanda  ") == "chanda"
    assert clean_search_term("a%b_c,d(e)*") == "a b c d e"
    assert clean_search_term("%%%") is None
    assert clean_search_term(None) is None
    assert clean_search_term("x" * 200) == "x" * 80


def test_people_by_ids_ignores_non_uuids_and_reads_emails() -> None:
    fake = Fake(dict(PEOPLE), AUTH_USERS)
    people = people_by_ids(fake, {TARGET, "not-a-uuid"})
    assert list(people) == [TARGET]
    assert people[TARGET] == {
        "user_id": TARGET,
        "display_name": "Chanda Mwale",
        "email": "chanda@example.test",
    }


def test_search_people_matches_names_and_emails() -> None:
    fake = Fake(dict(PEOPLE), AUTH_USERS)
    by_name = search_people(fake, "chanda")
    assert [p["user_id"] for p in by_name] == [TARGET]
    assert by_name[0]["email"] == "chanda@example.test"
    by_email = search_people(fake, "ops-only@")
    assert [p["user_id"] for p in by_email] == [OTHER]
    assert search_people(fake, TARGET)[0]["display_name"] == "Chanda Mwale"
    assert search_people(fake, "%%") == []


def test_search_people_survives_auth_search_failure() -> None:
    fake = Fake(dict(PEOPLE), AUTH_USERS)

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("gotrue down")

    fake.auth.admin.list_users = boom
    assert [p["user_id"] for p in search_people(fake, "chanda")] == [TARGET]


# ---------------------------------------------------------------------------
# Roles: assignments carry names; lookup replaces pasted UUIDs
# ---------------------------------------------------------------------------


def test_role_assignments_are_listed_by_name_and_email(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Fake(
        {
            **PEOPLE,
            "admin_roles": [
                {"key": "rbac_finance", "name": "Finance", "permissions": ["finance.read"]}
            ],
            "user_roles": [
                {"user_id": TARGET, "role": "rbac_finance"},
                {"user_id": USER, "role": "superadmin"},
            ],
        },
        AUTH_USERS,
    )
    body = _client(monkeypatch, fake).get("/admin/roles").json()
    by_user = {row["user_id"]: row for row in body["assignments"]}
    assert by_user[TARGET]["display_name"] == "Chanda Mwale"
    assert by_user[TARGET]["email"] == "chanda@example.test"
    assert by_user[USER]["display_name"] == "Founder King"


def test_account_lookup_finds_any_account_with_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Fake(
        {**PEOPLE, "user_roles": [{"user_id": TARGET, "role": "customer"}]},
        AUTH_USERS,
    )
    client = _client(monkeypatch, fake)
    response = client.get("/admin/accounts/lookup", params={"q": "chanda"})
    assert response.status_code == 200, response.text
    assert response.json()["accounts"] == [
        {
            "user_id": TARGET,
            "display_name": "Chanda Mwale",
            "email": "chanda@example.test",
            "roles": ["customer"],
        }
    ]
    assert client.get("/admin/accounts/lookup", params={"q": "c"}).status_code == 422


@pytest.mark.parametrize("roles", [frozenset({"admin"}), frozenset({"moderator"})])
def test_account_lookup_stays_superadmin_only(
    monkeypatch: pytest.MonkeyPatch, roles: frozenset[str]
) -> None:
    client = _client(monkeypatch, Fake(dict(PEOPLE), AUTH_USERS), roles)
    assert client.get("/admin/accounts/lookup", params={"q": "chanda"}).status_code == 403


# ---------------------------------------------------------------------------
# Accounts directory: search + pagination
# ---------------------------------------------------------------------------


def _directory_fake() -> Fake:
    return Fake(
        {
            **PEOPLE,
            "user_roles": [
                {"user_id": TARGET, "role": "admin"},
                {"user_id": USER, "role": "superadmin"},
                {"user_id": OTHER, "role": "rbac_ops"},
                {"user_id": OTHER, "role": "customer"},
            ],
        },
        AUTH_USERS,
    )


def test_accounts_directory_searches_name_email_and_role(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _directory_fake())
    by_name = client.get("/admin/accounts", params={"q": "chanda"}).json()
    assert [a["user_id"] for a in by_name["accounts"]] == [TARGET]
    assert by_name["total"] == 1
    by_email = client.get("/admin/accounts", params={"q": "ops-only@"}).json()
    assert [a["user_id"] for a in by_email["accounts"]] == [OTHER]
    by_role = client.get("/admin/accounts", params={"q": "superadmin"}).json()
    assert [a["user_id"] for a in by_role["accounts"]] == [USER]


def test_accounts_directory_pages_named_accounts_first(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _directory_fake())
    first = client.get("/admin/accounts", params={"limit": 2}).json()
    assert [a["display_name"] for a in first["accounts"]] == ["Chanda Mwale", "Founder King"]
    assert first["total"] == 3 and first["next_offset"] == 2
    second = client.get("/admin/accounts", params={"limit": 2, "offset": 2}).json()
    assert [a["user_id"] for a in second["accounts"]] == [OTHER]
    assert second["next_offset"] is None


# ---------------------------------------------------------------------------
# Audit log: actor/entity names and actor search
# ---------------------------------------------------------------------------


AUDIT_ROWS: list[dict[str, Any]] = [
    {
        "id": "a1",
        "at": "2026-11-25T10:00:00+00:00",
        "actor": USER,
        "actor_roles": ["superadmin"],
        "action": "admin.role.assign",
        "entity_type": "admin_role",
        "entity_id": TARGET,
        "outcome": "success",
        "request_id": None,
        "reason": None,
        "before": {"key": "rbac_finance", "value": None},
        "after": {"key": "rbac_finance", "value": {"role": "rbac_finance"}},
    },
    {
        "id": "a2",
        "at": "2026-11-25T09:00:00+00:00",
        "actor": TARGET,
        "actor_roles": ["admin"],
        "action": "admin.vendors.status",
        "entity_type": "vendor",
        "entity_id": VENDOR,
        "outcome": "success",
        "request_id": None,
        "reason": "KYC complete",
        "before": {"status": "pending"},
        "after": {"status": "active"},
    },
]


def _audit_fake() -> Fake:
    return Fake(
        {
            **PEOPLE,
            "audit_log": AUDIT_ROWS,
            "vendors": [{"id": VENDOR, "display_name": "Lusaka Electronics"}],
        },
        AUTH_USERS,
    )


def test_audit_entries_carry_actor_and_entity_names(monkeypatch: pytest.MonkeyPatch) -> None:
    items = _client(monkeypatch, _audit_fake()).get("/admin/audit-log").json()["items"]
    first, second = items
    assert first["actor_name"] == "Founder King"
    assert first["actor_email"] == "king@example.test"
    assert first["entity_label"] == "Chanda Mwale"
    assert second["actor_name"] == "Chanda Mwale"
    assert second["entity_label"] == "Lusaka Electronics"
    assert second["actor"] == TARGET


def test_audit_actor_filter_accepts_a_name_or_email(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _audit_fake()
    client = _client(monkeypatch, fake)
    by_name = client.get("/admin/audit-log", params={"actor_q": "chanda"})
    assert by_name.status_code == 200, by_name.text
    assert [item["id"] for item in by_name.json()["items"]] == ["a2"]
    assert ("actor", [TARGET]) in fake.calls_for("audit_log", "in_")

    nobody = client.get("/admin/audit-log", params={"actor_q": "nobody-here"})
    assert nobody.json() == {"items": [], "next_before": None, "next_before_id": None}
    assert client.get("/admin/audit-log", params={"actor_q": "%%"}).status_code == 422


def test_audit_name_search_keeps_the_audit_read_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _audit_fake(), frozenset({"admin"}))
    assert client.get("/admin/audit-log", params={"actor_q": "chanda"}).status_code == 403


def test_audit_actor_email_redacted_for_non_superadmin(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.auth import require_route_permission

    fake = _audit_fake()
    app = create_app()
    viewer = CurrentUser(id=USER, roles=frozenset({"rbac_auditor"}), token="t")
    app.dependency_overrides[require_route_permission] = lambda: viewer
    app.dependency_overrides[get_supabase_client] = lambda: fake
    app.dependency_overrides[get_supabase_service_client] = lambda: fake
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: fake)
    items = TestClient(app, raise_server_exceptions=False).get("/admin/audit-log").json()["items"]
    assert all(item.get("actor_email") in (None, "") for item in items)


def test_audit_actor_q_does_not_probe_non_actor_emails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Email of a user who never appears as audit actor must not match actor_q."""
    client = _client(monkeypatch, _audit_fake())
    response = client.get("/admin/audit-log", params={"actor_q": "ops-only@"})
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_before": None, "next_before_id": None}


def test_people_by_ids_pages_past_lookup_cap() -> None:
    ids = [f"10000000-0000-4000-8000-{i:012x}" for i in range(105)]
    fake = Fake({"profiles": [{"id": uid, "display_name": f"U{i}"} for i, uid in enumerate(ids)]})
    people = people_by_ids(fake, ids, with_email=False)
    assert len(people) == 105


# ---------------------------------------------------------------------------
# Catalog oversight: search + pagination, never an id as a title
# ---------------------------------------------------------------------------


def test_services_oversight_searches_filters_and_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    services = [
        {"id": f"s{i}", "vendor_id": VENDOR, "title": f"Logo design {i}", "status": "active"}
        for i in range(3)
    ] + [{"id": "s9", "vendor_id": VENDOR, "title": "Plumbing", "status": "paused"}]
    fake = Fake({"services": services})
    client = _client(monkeypatch, fake, frozenset({"admin"}))
    page = client.get("/admin/services", params={"q": "logo", "limit": 2}).json()
    assert [item["id"] for item in page["items"]] == ["s0", "s1"]
    assert page["total"] == 3 and page["next_offset"] == 2
    assert ("title", "%logo%") in fake.calls_for("services", "ilike")
    last = client.get("/admin/services", params={"q": "logo", "limit": 2, "offset": 2}).json()
    assert [item["id"] for item in last["items"]] == ["s2"] and last["next_offset"] is None
    paused = client.get("/admin/services", params={"status": "paused"}).json()
    assert [item["id"] for item in paused["items"]] == ["s9"]
    assert client.get("/admin/services", params={"status": "Bad;"}).status_code == 422


def test_inventory_oversight_matches_product_names_and_never_shows_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Fake(
        {
            "products": [{"id": "p1", "name": "Hisense TV"}],
            "vendor_listings": [
                {
                    "id": "l1",
                    "vendor_id": VENDOR,
                    "product_id": "p1",
                    "title_override": None,
                    "stock_mode": "tracked",
                    "stock_qty": 2,
                    "status": "active",
                    "products": None,
                }
            ],
        }
    )
    client = _client(monkeypatch, fake, frozenset({"admin"}))
    body = client.get("/admin/inventory", params={"q": "hisense"}).json()
    assert fake.calls_for("vendor_listings", "or_") == [
        ("title_override.ilike.%hisense%,product_id.in.(p1)",)
    ]
    assert body["items"][0]["display_title"] is None
    assert body["total"] == 1


def test_inventory_hostile_q_adds_no_extra_or_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Fake({"products": [], "vendor_listings": []})
    client = _client(monkeypatch, fake, frozenset({"admin"}))
    response = client.get("/admin/inventory", params={"q": "tv,status.eq.active),(x"})
    assert response.status_code == 200
    for (clause,) in fake.calls_for("vendor_listings", "or_"):
        parts = clause.split(",")
        assert all(part.startswith(("title_override.ilike.", "product_id.in.")) for part in parts)
        assert "(x" not in clause and ")" not in clause.replace("product_id.in.(", "")
