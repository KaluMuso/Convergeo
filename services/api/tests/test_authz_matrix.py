"""Route x role authorization matrix — the API-layer authz enforcement backbone.

Complements the DB-layer RLS isolation matrix (``tests/rls/test_matrix.py``): that
proves row ownership at the database; this proves the FastAPI authz *guard* layer
(authentication requirement + role gating) for every route x persona, and that no
new route slips in unauthenticated by accident.

Design — isolation-clean / no-DB (runs under the plain ``python`` CI job):
  * Every route is enumerated from the live app and classified into an auth class.
  * ALLOW cells are asserted structurally (the route's dependency guard requires
    exactly that auth class / role), so no request handler ever executes.
  * DENY cells are asserted with live requests that short-circuit *inside* the auth
    guard (missing bearer -> 401; wrong role -> 403; missing internal token -> 401;
    unsigned webhook -> >=400) *before* any DB / service-client call, so the suite
    needs no Postgres.
  * Any route that is dependency-public but not in the explicit PUBLIC/SIGNED
    registry fails the coverage test — this is the trip-wire that catches a new
    business route accidentally shipped without an authz guard (OWASP A01).

IDOR: authenticated cross-owner isolation (another owner's id -> 403/404, never 200)
is enforced by RLS and proven at the DB layer by ``tests/rls`` and live by
``scripts/security/pentest-lite.sh``. Here we assert the *necessary* API-boundary
condition: every id-bearing protected route denies anon (401) and cross-role (403),
so no object reference is reachable without first passing ownership-scoped RLS.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from dataclasses import dataclass
from enum import StrEnum

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.main import create_app
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Personas (mirror the RLS isolation matrix persona set)
# ---------------------------------------------------------------------------


class Persona(StrEnum):
    ANON = "anon"
    CUSTOMER = "customer"
    OTHER_CUSTOMER = "other-customer"
    VENDOR = "vendor"
    OTHER_VENDOR = "other-vendor"
    ADMIN = "admin"


# Role set each persona authenticates with (OTHER_* differ only by owner id, which
# matters for IDOR — enforced by RLS, not by the role guard).
PERSONA_ROLES: dict[Persona, frozenset[str]] = {
    Persona.ANON: frozenset(),
    Persona.CUSTOMER: frozenset({"customer"}),
    Persona.OTHER_CUSTOMER: frozenset({"customer"}),
    Persona.VENDOR: frozenset({"vendor"}),
    Persona.OTHER_VENDOR: frozenset({"vendor"}),
    Persona.ADMIN: frozenset({"admin"}),
}

PERSONA_OWNER_ID: dict[Persona, str] = {
    Persona.ANON: "",
    Persona.CUSTOMER: "00000000-0000-0000-0000-0000000c0001",
    Persona.OTHER_CUSTOMER: "00000000-0000-0000-0000-0000000c0002",
    Persona.VENDOR: "00000000-0000-0000-0000-0000000e0001",
    Persona.OTHER_VENDOR: "00000000-0000-0000-0000-0000000e0002",
    Persona.ADMIN: "00000000-0000-0000-0000-0000000a0001",
}

ALL_PERSONAS = list(Persona)

Outcome = str  # "allow" | "deny"


class AuthClass(StrEnum):
    PUBLIC_OPEN = "public-open"  # truly unauthenticated by design (discovery/commerce)
    SIGNED_LINK = "signed-link"  # HMAC token in query (invoice download)
    INTERNAL_TOKEN = "internal-token"  # shared X-Internal-Token, machine-to-machine
    WEBHOOK_SIGNED = "webhook-signed"  # provider signature / verify token
    AUTH_ANY = "auth-any"  # any authenticated user
    ROLE = "role"  # require_role(...) gated


# ---------------------------------------------------------------------------
# Explicit registry of intentionally-unauthenticated routes.
# A dependency-public route absent from here fails the coverage trip-wire.
# ---------------------------------------------------------------------------

PUBLIC_OPEN_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/ask"),
        ("POST", "/auth/guard/otp-quota"),
        # M16-P09 beta gate: pre-login invite gate + feedback. redeem/gate are
        # inherently pre-auth; feedback is optional-auth (attaches user_id if a
        # valid token is present) — all IP rate-limited. Admin invite routes
        # (/beta/invites) are role-guarded and classified automatically.
        ("GET", "/beta/gate"),
        ("POST", "/beta/redeem"),
        ("POST", "/beta/feedback"),
        ("GET", "/cart"),
        ("POST", "/cart/items"),
        ("DELETE", "/cart/items/{listing_id}"),
        ("PATCH", "/cart/items/{listing_id}"),
        ("GET", "/catalog/listings"),
        ("GET", "/directory"),
        ("GET", "/directory/{slug}"),
        ("GET", "/events"),
        ("GET", "/events/{slug}"),
        ("GET", "/events/{slug}/calendar.ics"),
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/merch/slots"),
        ("GET", "/products/{slug}"),
        ("GET", "/products/{slug}/comparison"),
        ("GET", "/reviews"),
        ("GET", "/search"),
        ("GET", "/search/suggest"),
        ("GET", "/services"),
        ("GET", "/services/{slug}"),
    }
)

SIGNED_LINK_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/invoices/download"),
    }
)


# ---------------------------------------------------------------------------
# Route enumeration + guard detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteEntry:
    method: str
    path: str
    auth_class: AuthClass
    required_roles: frozenset[str]

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)

    @property
    def has_id_param(self) -> bool:
        return "{" in self.path


def _iter_api_routes(app: FastAPI) -> Generator[APIRoute, None, None]:
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route
        # FastAPI >=0.130 wraps include_router() results in _IncludedRouter, which
        # exposes the underlying APIRouter via `original_router`.
        original = getattr(route, "original_router", None)
        if original is not None:
            for sub in getattr(original, "routes", []):
                if isinstance(sub, APIRoute):
                    yield sub


def _detect_dependency_guard(route: APIRoute) -> tuple[bool, frozenset[str]]:
    """Return (requires_authenticated_user, required_roles) from the dependant tree."""
    roles: set[str] = set()
    has_current_user = False
    stack = [route.dependant]
    seen: set[int] = set()
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        call = dep.call
        if call is get_current_user:
            has_current_user = True
        # require_role(...) returns a closure named `_require_role` closing over the
        # required-role frozenset.
        if call is not None and getattr(call, "__name__", "") == "_require_role":
            for cell in getattr(call, "__closure__", None) or ():
                value = cell.cell_contents
                if isinstance(value, frozenset):
                    roles |= {r for r in value if isinstance(r, str)}
        stack.extend(dep.dependencies)
    return has_current_user, frozenset(roles)


def _classify(route: APIRoute, method: str) -> RouteEntry:
    path = route.path
    if path.startswith("/internal/"):
        return RouteEntry(method, path, AuthClass.INTERNAL_TOKEN, frozenset())
    if path.startswith("/webhooks/"):
        return RouteEntry(method, path, AuthClass.WEBHOOK_SIGNED, frozenset())

    has_user, roles = _detect_dependency_guard(route)
    if roles:
        return RouteEntry(method, path, AuthClass.ROLE, roles)
    if has_user:
        return RouteEntry(method, path, AuthClass.AUTH_ANY, frozenset())

    key = (method, path)
    if key in SIGNED_LINK_ROUTES:
        return RouteEntry(method, path, AuthClass.SIGNED_LINK, frozenset())
    if key in PUBLIC_OPEN_ROUTES:
        return RouteEntry(method, path, AuthClass.PUBLIC_OPEN, frozenset())
    # Unclassified dependency-public route -> coverage trip-wire (see test below).
    return RouteEntry(method, path, AuthClass.PUBLIC_OPEN, frozenset({"__UNREGISTERED__"}))


def _build_matrix() -> list[RouteEntry]:
    app = create_app()
    entries: list[RouteEntry] = []
    seen: set[tuple[str, str]] = set()
    for route in _iter_api_routes(app):
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
            entry = _classify(route, method)
            if entry.key in seen:
                continue
            seen.add(entry.key)
            entries.append(entry)
    entries.sort(key=lambda e: (e.path, e.method))
    return entries


ROUTES: list[RouteEntry] = _build_matrix()

# Protected routes = anything that requires *some* credential (auth/role/token/sig).
PROTECTED_CLASSES = {
    AuthClass.AUTH_ANY,
    AuthClass.ROLE,
    AuthClass.INTERNAL_TOKEN,
    AuthClass.WEBHOOK_SIGNED,
}


def expected_outcome(entry: RouteEntry, persona: Persona) -> Outcome:
    """Guard-layer expectation for (route, persona): 'allow' passes the authz guard."""
    cls = entry.auth_class
    if cls in (AuthClass.PUBLIC_OPEN, AuthClass.SIGNED_LINK):
        return "allow"
    if cls in (AuthClass.INTERNAL_TOKEN, AuthClass.WEBHOOK_SIGNED):
        # Machine-to-machine: no user persona carries the shared token/signature.
        return "deny"
    if cls is AuthClass.AUTH_ANY:
        return "deny" if persona is Persona.ANON else "allow"
    # ROLE
    if persona is Persona.ANON:
        return "deny"
    return "allow" if PERSONA_ROLES[persona] & entry.required_roles else "deny"


# ---------------------------------------------------------------------------
# Live client helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def app_instance() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app_instance: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app_instance, raise_server_exceptions=False) as test_client:
        yield test_client


def _concrete(path: str) -> str:
    # Any syntactically valid uuid/slug: denial short-circuits before the handler,
    # so the exact value is irrelevant.
    return re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-0000000000id", path)


def _override_user(app: FastAPI, persona: Persona) -> None:
    roles = PERSONA_ROLES[persona]
    owner = PERSONA_OWNER_ID[persona]

    def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=owner, roles=roles, token="test-token")

    app.dependency_overrides[get_current_user] = _fake_current_user


def _request(client: TestClient, entry: RouteEntry) -> int:
    body: dict[str, object] | None = {} if entry.method in {"POST", "PATCH", "PUT"} else None
    response = client.request(entry.method, _concrete(entry.path), json=body)
    return int(response.status_code)


# ---------------------------------------------------------------------------
# Coverage / completeness
# ---------------------------------------------------------------------------


def test_every_route_is_classified() -> None:
    """Trip-wire: no business route may be dependency-public without being registered."""
    unregistered = [e for e in ROUTES if "__UNREGISTERED__" in e.required_roles]
    assert not unregistered, (
        "Unclassified dependency-public route(s) — a new endpoint may lack an authz "
        "guard, or must be added to PUBLIC_OPEN_ROUTES/SIGNED_LINK_ROUTES: "
        f"{[e.key for e in unregistered]}"
    )
    assert ROUTES, "no routes enumerated"


def test_matrix_covers_every_route_times_role() -> None:
    """100% route x role coverage — every cell has a defined expected outcome."""
    cells = 0
    for entry in ROUTES:
        for persona in ALL_PERSONAS:
            outcome = expected_outcome(entry, persona)
            assert outcome in ("allow", "deny")
            cells += 1
    assert cells == len(ROUTES) * len(ALL_PERSONAS)


def test_matrix_summary(capsys: pytest.CaptureFixture[str]) -> None:
    from collections import Counter

    by_class = Counter(e.auth_class.value for e in ROUTES)
    id_routes = [e for e in ROUTES if e.has_id_param and e.auth_class in PROTECTED_CLASSES]
    allow = sum(
        1 for e in ROUTES for p in ALL_PERSONAS if expected_outcome(e, p) == "allow"
    )
    deny = len(ROUTES) * len(ALL_PERSONAS) - allow
    with capsys.disabled():
        print("\n[authz-matrix] route x method =", len(ROUTES))
        print("[authz-matrix] cells (routes x 6 personas) =", len(ROUTES) * len(ALL_PERSONAS))
        print("[authz-matrix]   allow =", allow, " deny =", deny)
        print("[authz-matrix] by auth class =", dict(sorted(by_class.items())))
        print("[authz-matrix] protected id-param routes (IDOR surface) =", len(id_routes))


# ---------------------------------------------------------------------------
# DENY assertions — live, guard short-circuits before any DB call
# ---------------------------------------------------------------------------

_ANON_PROTECTED = [e for e in ROUTES if e.auth_class in (AuthClass.AUTH_ANY, AuthClass.ROLE)]


@pytest.mark.parametrize("entry", _ANON_PROTECTED, ids=lambda e: f"{e.method} {e.path}")
def test_anonymous_denied_on_protected_routes(client: TestClient, entry: RouteEntry) -> None:
    """Anon must be rejected (401) by every authenticated/role route before the handler."""
    assert expected_outcome(entry, Persona.ANON) == "deny"
    status = _request(client, entry)
    assert status == 401, f"{entry.method} {entry.path}: anon expected 401, got {status}"


_ROLE_ROUTES = [e for e in ROUTES if e.auth_class is AuthClass.ROLE]
_WRONG_ROLE_CASES = [
    (e, p)
    for e in _ROLE_ROUTES
    for p in ALL_PERSONAS
    if p is not Persona.ANON and expected_outcome(e, p) == "deny"
]


@pytest.mark.parametrize(
    ("entry", "persona"),
    _WRONG_ROLE_CASES,
    ids=lambda x: f"{x.method} {x.path}" if isinstance(x, RouteEntry) else x.value,
)
def test_wrong_role_denied(app_instance: FastAPI, entry: RouteEntry, persona: Persona) -> None:
    """An authenticated user lacking the required role gets 403 (never reaches handler)."""
    _override_user(app_instance, persona)
    try:
        with TestClient(app_instance, raise_server_exceptions=False) as c:
            status = _request(c, entry)
    finally:
        app_instance.dependency_overrides.clear()
    assert status == 403, (
        f"{entry.method} {entry.path}: persona {persona.value} expected 403, got {status} "
        f"(route requires {sorted(entry.required_roles)})"
    )


_INTERNAL_ROUTES = [e for e in ROUTES if e.auth_class is AuthClass.INTERNAL_TOKEN]


@pytest.mark.parametrize("entry", _INTERNAL_ROUTES, ids=lambda e: f"{e.method} {e.path}")
def test_internal_endpoints_require_token(client: TestClient, entry: RouteEntry) -> None:
    """Every /internal/* endpoint rejects a request with no shared token (401)."""
    status = _request(client, entry)
    assert status == 401, f"{entry.method} {entry.path}: no-token expected 401, got {status}"


_WEBHOOK_ROUTES = [e for e in ROUTES if e.auth_class is AuthClass.WEBHOOK_SIGNED]


@pytest.mark.parametrize("entry", _WEBHOOK_ROUTES, ids=lambda e: f"{e.method} {e.path}")
def test_webhook_endpoints_reject_unsigned(client: TestClient, entry: RouteEntry) -> None:
    """Webhook endpoints never process an unsigned/unverified request (status >= 400)."""
    status = _request(client, entry)
    assert status >= 400, (
        f"{entry.method} {entry.path}: unsigned webhook must not be accepted, got {status}"
    )


# ---------------------------------------------------------------------------
# IDOR — API-boundary necessary condition (no unauthenticated object reference)
# ---------------------------------------------------------------------------

_ID_PROTECTED = [e for e in ROUTES if e.has_id_param and e.auth_class in PROTECTED_CLASSES]


@pytest.mark.parametrize("entry", _ID_PROTECTED, ids=lambda e: f"{e.method} {e.path}")
def test_idor_id_routes_deny_anonymous(client: TestClient, entry: RouteEntry) -> None:
    """No id-bearing protected route may be reached anonymously (never 200 with an id).

    Authenticated cross-owner isolation (other-owner id -> 403/404) is proven at the DB
    layer by tests/rls and live by scripts/security/pentest-lite.sh.
    """
    status = _request(client, entry)
    assert status != 200, f"{entry.method} {entry.path}: anon reached an object reference"
    assert status in (401, 403), (
        f"{entry.method} {entry.path}: expected auth denial (401/403), got {status}"
    )


# ---------------------------------------------------------------------------
# ALLOW cells — structural (no handler executes)
# ---------------------------------------------------------------------------


def test_public_routes_have_no_auth_guard() -> None:
    """Registered public routes must genuinely carry no bearer/role dependency."""
    app = create_app()
    guard_by_key: dict[tuple[str, str], tuple[bool, frozenset[str]]] = {}
    for route in _iter_api_routes(app):
        has_user, roles = _detect_dependency_guard(route)
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
            guard_by_key[(method, route.path)] = (has_user, roles)

    for key in PUBLIC_OPEN_ROUTES | SIGNED_LINK_ROUTES:
        has_user, roles = guard_by_key.get(key, (False, frozenset()))
        assert not has_user and not roles, (
            f"{key} is registered public but carries an auth dependency "
            f"(user={has_user}, roles={sorted(roles)})"
        )


def test_role_routes_expose_expected_role_guard() -> None:
    """Sanity: role-gated routes require only known personas' roles (allow cells valid)."""
    known = {"customer", "vendor", "admin"}
    for entry in _ROLE_ROUTES:
        assert entry.required_roles, f"{entry.key} classified ROLE but no roles detected"
        unknown = entry.required_roles - known
        assert not unknown, f"{entry.key} requires unmodeled role(s) {sorted(unknown)}"
        # At least one persona must be able to satisfy each role route (no dead route).
        assert any(
            expected_outcome(entry, p) == "allow" for p in ALL_PERSONAS
        ), f"{entry.key} is unreachable by any modeled persona"
