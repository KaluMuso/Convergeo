#!/usr/bin/env python3
"""WP-1B — production-container Cash-on-Delivery smoke test.

Validates the *actual API runtime image* (``infra/api.Dockerfile``), not merely the
development environment: it starts the built image against an isolated Postgres, seeds
the real schema plus a minimal COD fixture, and drives one Cash-on-Delivery order
through the running container's HTTP API
(``POST /admin/orders/{order_id}/cod/confirm-collection``).

By querying Postgres directly afterwards it asserts the container:

* **order created / settled** — the seeded COD order moves ``delivered -> completed``;
* **audit entry with transaction-local actor/note context** — the ``0014`` audit
  trigger wrote an ``order_events`` row carrying the ``app.order_actor`` /
  ``app.order_note`` GUCs that ``transition_order`` sets in the *same* SQL script.
  This is the guarantee WP-1A's native psycopg adapter must preserve (one logical
  script == one transaction on one connection); if the adapter split ``set_config``
  from the ``UPDATE`` the note would arrive ``NULL``. The note round-trips from the
  HTTP request body all the way to the trigger, so a correct assertion proves the
  whole path end-to-end inside the container;
* **required ledger/commission entries posted** — ``cod_collected`` +
  ``commission_capture`` + ``release_to_vendor`` (preceded by the order-time COD
  receivable), each double-entry balanced;
* **order/escrow state consistent** — escrow nets back to zero and the order is
  ``completed``.

The only Supabase surface the admin COD path touches is auth: a JWKS document and one
``user_roles`` read. Both are served by a tiny in-process stub, authenticated with a
self-minted RS256 token, so the test uses **no Lenco, WhatsApp, external network, or
production credentials** — everything is localhost.

Two failure modes are called out explicitly (WP-1B):

* **the image cannot connect to Postgres**, and
* **database access regresses to a missing subprocess/binary dependency** — e.g.
  reverting WP-1A back to shelling out to ``psql``, which is absent from the
  ``python:3.12-slim`` runtime image.

Either one makes the COD call fail; the runner then attaches the container logs and
exits non-zero. As a positive guard the smoke test also asserts the running image
carries **no ``psql`` binary**, so a green run proves the write path is genuinely the
in-process native adapter and not a shelled-out client.

Usage (from ``services/api``)::

    uv run python tests/container/cod_container_smoke.py

Requires Docker and ``psql`` on the host and ``SUPABASE_DB_URL`` pointing at an
isolated Postgres (defaults to ``127.0.0.1:5432``). The image tag is taken from
``VERGEO5_API_IMAGE`` (default ``vergeo5-api:cod-smoke``); if that image is absent it
is built from ``infra/api.Dockerfile`` on the spot.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATION_REPLAY = REPO_ROOT / "scripts" / "ci" / "migration-replay.sh"
API_DOCKERFILE = REPO_ROOT / "infra" / "api.Dockerfile"

# --------------------------------------------------------------------------- #
# Fixed identifiers for the COD scenario. Vendor / customer / owner ids match the
# demo fixture ids (services/api/tests/fixtures/demo/ids.json) so the scenario reads
# the same as the rest of the suite; the ledger-account ids mirror tests/test_cod.py.
# --------------------------------------------------------------------------- #
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_OWNER_ID = "33333333-3333-3333-3333-333333333333"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"

PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"
FEES_ID = "c4000000-0000-0000-0000-000000000004"
VENDOR_PAYABLE_ID = "c5000000-0000-0000-0000-000000000005"
COD_RECEIVABLE_ID = "c6000000-0000-0000-0000-000000000006"

CHECKOUT_GROUP_ID = "c0000000-0000-0000-0000-0000000000c0"
ORDER_ID = "0d000000-0000-0000-0000-00000000000d"
ORDER_ITEM_ID = "01000000-0000-0000-0000-000000000001"
SNAPSHOT_LISTING_ID = "11110000-0000-0000-0000-000000000011"

# System actor the COD state-machine transition stamps into the audit row. Imported
# from the app so it can never drift from the runtime value.
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
from app.services.orders.state import SYSTEM_ACTOR_ID  # noqa: E402

SUBTOTAL_NGWEE = 180_000
DELIVERY_FEE_NGWEE = 20_000
COLLECTABLE_NGWEE = SUBTOTAL_NGWEE + DELIVERY_FEE_NGWEE  # 200_000
RATE_BPS = 500
COMMISSION_NGWEE = (SUBTOTAL_NGWEE * RATE_BPS) // 10_000  # 9_000
NET_VENDOR_NGWEE = COLLECTABLE_NGWEE - COMMISSION_NGWEE  # 191_000

# Distinctive note so the assertion proves it round-trips: HTTP body -> app.order_note
# GUC -> 0014 audit trigger -> order_events.note, all inside the container transaction.
COD_NOTE = "WP-1B container smoke: cash collected at the door"

DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/postgres"
DEFAULT_IMAGE = "vergeo5-api:cod-smoke"
CONTAINER_PORT = 8000
JWT_KID = "wp1b-smoke-key"


class SmokeError(RuntimeError):
    """A smoke-test assertion or setup step failed."""


def log(message: str) -> None:
    print(f"[cod-smoke] {message}", flush=True)


# --------------------------------------------------------------------------- #
# Host-side Postgres access (psql — the runner has it; the container must NOT need it).
# --------------------------------------------------------------------------- #


def psql(dsn: str, sql: str) -> list[str]:
    """Run one statement, return non-empty ``-At`` output rows. Raises on error."""
    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeError(f"psql failed: {proc.stderr.strip()}\n  SQL: {sql[:200]}")
    return [line for line in proc.stdout.splitlines() if line]


def psql_script(dsn: str, script: str) -> None:
    """Run a multi-statement script (stdin). Raises on error."""
    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-At"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeError(f"psql script failed: {proc.stderr.strip()}")


def reset_and_apply_schema(dsn: str) -> None:
    """Drop and rebuild the schema, then replay the real migrations onto bare Postgres.

    Reuses ``scripts/ci/migration-replay.sh`` — the same proven Dockerless shim
    (Supabase roles, ``auth`` schema/functions, pgvector) + migration replay the
    ``migrations`` CI job runs — so the container talks to the true production schema.
    """
    log("resetting schema (public + auth)")
    psql_script(
        dsn,
        "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
        "DROP SCHEMA IF EXISTS auth CASCADE;"
        "DROP SCHEMA IF EXISTS extensions CASCADE;",
    )

    parsed = urlparse(dsn)
    env = {
        **os.environ,
        "PGHOST": parsed.hostname or "127.0.0.1",
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": parsed.username or "postgres",
        "PGPASSWORD": parsed.password or "postgres",
        "PGDATABASE": (parsed.path or "/postgres").lstrip("/") or "postgres",
    }
    log("replaying migrations via scripts/ci/migration-replay.sh")
    proc = subprocess.run(
        ["bash", str(MIGRATION_REPLAY)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeError(
            "migration replay failed:\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )


def seed_cod_scenario(dsn: str) -> None:
    """Seed one delivered Cash-on-Delivery order plus the ledger chart of accounts.

    * two ``auth.users`` (customer + vendor owner) — the ``handle_new_user`` trigger
      (migration 0010) auto-creates their ``profiles`` + default ``customer`` role;
    * one ``active`` vendor owned by the vendor owner;
    * the six ledger accounts the COD collection posts against;
    * a ``completed`` checkout group and a ``delivered`` COD order (+ one item) with an
      immutable commission snapshot at ``RATE_BPS``.

    Everything runs as the ``postgres`` superuser, which bypasses RLS — exactly how the
    container's ``SUPABASE_DB_URL`` connection behaves.
    """
    log("seeding COD scenario (vendor, customer, ledger accounts, delivered COD order)")
    snapshot = {
        "lines": [
            {
                "listing_id": SNAPSHOT_LISTING_ID,
                "category_key": "electronics",
                "rate_bps": RATE_BPS,
                "qty": 1,
                "unit_price_ngwee": SUBTOTAL_NGWEE,
                "line_total_ngwee": SUBTOTAL_NGWEE,
                "wholesale": False,
            }
        ]
    }
    snapshot_sql = json.dumps(snapshot, separators=(",", ":")).replace("'", "''")

    script = f"""
BEGIN;

-- auth.users -> handle_new_user() trigger seeds profiles + default customer role.
INSERT INTO auth.users (id) VALUES ('{CUSTOMER_ID}') ON CONFLICT (id) DO NOTHING;
INSERT INTO auth.users (id) VALUES ('{VENDOR_OWNER_ID}') ON CONFLICT (id) DO NOTHING;

INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
VALUES (
  '{VENDOR_ID}', '{VENDOR_OWNER_ID}', 'shop-a-cod-smoke', 'Shop A (COD smoke)', 'active', 2
) ON CONFLICT (id) DO NOTHING;

INSERT INTO public.ledger_accounts (id, kind) VALUES
  ('{PLATFORM_CASH_ID}', 'platform_cash'),
  ('{ESCROW_ID}', 'escrow'),
  ('{COMMISSION_ID}', 'commission_revenue'),
  ('{FEES_ID}', 'fees')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.ledger_accounts (id, kind, vendor_id) VALUES
  ('{VENDOR_PAYABLE_ID}', 'vendor_payable', '{VENDOR_ID}'),
  ('{COD_RECEIVABLE_ID}', 'cod_receivable', '{VENDOR_ID}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES (
  '{CHECKOUT_GROUP_ID}', '{CUSTOMER_ID}', 'cod-smoke-{CHECKOUT_GROUP_ID}',
  {SUBTOTAL_NGWEE}, {DELIVERY_FEE_NGWEE}, {COLLECTABLE_NGWEE}, 'completed'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
  delivery_fee_ngwee, cod, commission_snapshot
) VALUES (
  '{ORDER_ID}', '{CHECKOUT_GROUP_ID}', '{VENDOR_ID}', '{CUSTOMER_ID}', 'delivered', 'delivery',
  {DELIVERY_FEE_NGWEE}, true, '{snapshot_sql}'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO public.order_items (id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot)
VALUES ('{ORDER_ITEM_ID}', '{ORDER_ID}', 'product', 1, {SUBTOTAL_NGWEE}, 'COD smoke item')
ON CONFLICT (id) DO NOTHING;

COMMIT;
"""
    psql_script(dsn, script)

    # Guard the fixture itself: a delivered, COD order must exist before we drive it.
    rows = psql(dsn, f"SELECT status FROM public.orders WHERE id = '{ORDER_ID}' AND cod = true;")
    if rows != ["delivered"]:
        raise SmokeError(f"COD order fixture not in expected state: {rows!r}")


# --------------------------------------------------------------------------- #
# Minimal Supabase auth stub: JWKS + one user_roles read. Self-minted RS256 token.
# --------------------------------------------------------------------------- #


@dataclass
class AuthContext:
    issuer: str
    supabase_url: str
    token: str


def _build_keypair() -> tuple[Any, dict[str, Any]]:
    """Generate an RSA keypair and its public JWK (kid=JWT_KID)."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": JWT_KID, "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _mint_admin_jwt(private_key: Any, issuer: str) -> str:
    import jwt

    now = int(time.time())
    claims = {
        "sub": ADMIN_ID,
        "aud": "authenticated",
        "role": "authenticated",
        "iss": issuer,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": JWT_KID})


def _make_stub_handler(public_jwk: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    jwks_body = json.dumps({"keys": [public_jwk]}).encode()
    user_roles_body = json.dumps([{"role": "admin"}]).encode()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if "jwks.json" in self.path:
                self._send(jwks_body)
            elif "/rest/v1/user_roles" in self.path:
                self._send(user_roles_body)
            else:
                # Any other PostgREST read (defensive) -> empty result set.
                self._send(b"[]")

        def do_POST(self) -> None:  # noqa: N802
            self._send(b"[]")

        def log_message(self, *args: object) -> None:  # silence per-request logging
            return

    return Handler


def start_auth_stub() -> tuple[ThreadingHTTPServer, AuthContext]:
    private_key, public_jwk = _build_keypair()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_stub_handler(public_jwk))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    supabase_url = f"http://127.0.0.1:{port}"
    issuer = f"{supabase_url}/auth/v1"
    token = _mint_admin_jwt(private_key, issuer)
    log(f"auth stub on {supabase_url} (JWKS + user_roles), admin token minted")
    return server, AuthContext(issuer=issuer, supabase_url=supabase_url, token=token)


# --------------------------------------------------------------------------- #
# Docker: build (if needed), run, health-gate, teardown.
# --------------------------------------------------------------------------- #


def _docker(
    *args: str, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=capture,
        text=True,
        check=check,
    )


def ensure_image(image: str) -> None:
    exists = _docker("image", "inspect", image, check=False, capture=True).returncode == 0
    if exists:
        log(f"using existing image {image}")
        return
    log(f"building image {image} from infra/api.Dockerfile (context = repo root)")
    _docker(
        "build",
        "-f",
        str(API_DOCKERFILE),
        "-t",
        image,
        str(REPO_ROOT),
    )


def run_container(image: str, name: str, dsn: str, supabase_url: str) -> None:
    """Start the real image against the isolated Postgres, host-networked.

    Host networking lets the container reach the runner's Postgres and the auth stub on
    127.0.0.1 while the app listens on the host's :8000 — no image change, just runtime
    flags. ``ENV=production`` exercises the production settings path.
    """
    log(f"docker run {image} (name={name}, --network host)")
    _docker(
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "host",
        "-e",
        f"SUPABASE_URL={supabase_url}",
        "-e",
        "SUPABASE_ANON_KEY=cod-smoke-anon-key",
        "-e",
        "SUPABASE_SERVICE_ROLE_KEY=cod-smoke-service-role-key",
        "-e",
        f"SUPABASE_DB_URL={dsn}",
        "-e",
        "ENV=production",
        "-e",
        "CORS_ORIGINS=https://smoke.vergeo5.test",
        "-e",
        "LOG_LEVEL=INFO",
        image,
    )


def container_logs(name: str) -> str:
    result = _docker("logs", name, check=False, capture=True)
    return (result.stdout or "") + (result.stderr or "")


def stop_container(name: str) -> None:
    _docker("rm", "-f", name, check=False, capture=True)


def wait_for_health(base_url: str, name: str, timeout: float = 60.0) -> None:
    import httpx

    deadline = time.time() + timeout
    last_err: str = "no attempt"
    while time.time() < deadline:
        running = _docker(
            "inspect", "-f", "{{.State.Running}}", name, check=False, capture=True
        ).stdout.strip()
        if running == "false":
            raise SmokeError(f"container exited during startup:\n{container_logs(name)[-3000:]}")
        try:
            resp = httpx.get(f"{base_url}/healthz", timeout=2.0)
            if resp.status_code == 200:
                log("container healthy (GET /healthz -> 200)")
                return
            last_err = f"status {resp.status_code}"
        except Exception as exc:  # not up yet
            last_err = repr(exc)
        time.sleep(1.0)
    raise SmokeError(
        f"container did not become healthy in {timeout}s (last: {last_err})\n"
        f"{container_logs(name)[-3000:]}"
    )


def assert_no_psql_binary(name: str) -> None:
    """The runtime image must not carry a psql client — WP-1A's adapter is in-process.

    A green COD flow with no psql present proves the write path is the native psycopg
    adapter, not a shelled-out binary that happens to be baked into the image.
    """
    probe = _docker(
        "exec",
        name,
        "sh",
        "-c",
        "command -v psql || echo __NO_PSQL__",
        check=False,
        capture=True,
    )
    if "__NO_PSQL__" not in probe.stdout:
        raise SmokeError(
            "runtime image unexpectedly bundles a psql binary — the native adapter "
            f"must not depend on a subprocess client (found: {probe.stdout.strip()})"
        )
    log("runtime image carries no psql binary (native adapter is in-process)")


# --------------------------------------------------------------------------- #
# Drive the COD order through the real API + assert the persisted outcome.
# --------------------------------------------------------------------------- #


def drive_cod_confirmation(base_url: str, token: str, name: str) -> dict[str, object]:
    import httpx

    url = f"{base_url}/admin/orders/{ORDER_ID}/cod/confirm-collection"
    log(f"POST {url} (admin COD confirm) through the running container")
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"note": COD_NOTE},
            timeout=15.0,
        )
    except Exception as exc:  # pragma: no cover - network-level failure
        raise SmokeError(
            f"COD request never completed ({exc!r}) — container may be unable to reach "
            f"Postgres.\n{container_logs(name)[-3000:]}"
        ) from exc

    if resp.status_code != 200:
        logs = container_logs(name)
        hint = _diagnose_failure(logs)
        raise SmokeError(
            f"COD confirm returned {resp.status_code}: {resp.text}\n{hint}\n"
            f"--- container logs (tail) ---\n{logs[-4000:]}"
        )
    body = cast("dict[str, object]", resp.json())
    log(f"container responded 200: {json.dumps(body)}")
    return body


def _diagnose_failure(logs: str) -> str:
    """Name the two WP-1B failure modes when their signatures show up in the logs."""
    lower = logs.lower()
    if "psql" in lower and ("no such file" in lower or "filenotfound" in lower):
        return (
            "DIAGNOSIS: database access regressed to a missing subprocess/binary "
            "dependency — the image tried to exec `psql`, which the runtime image does "
            "not contain. The native psycopg adapter (WP-1A) must be the sole write path."
        )
    connect_signatures = (
        "could not connect",
        "connection refused",
        "pool",
        "operationalerror",
        "timeout expired",
    )
    if any(sig in lower for sig in connect_signatures):
        return (
            "DIAGNOSIS: the image could not connect to Postgres "
            "(check SUPABASE_DB_URL / reachability)."
        )
    return "DIAGNOSIS: unexpected server error (see container logs below)."


def assert_api_response(body: dict[str, object]) -> None:
    expected = {
        "order_id": ORDER_ID,
        "collectable_ngwee": COLLECTABLE_NGWEE,
        "commission_ngwee": COMMISSION_NGWEE,
        "net_vendor_ngwee": NET_VENDOR_NGWEE,
        "idempotent_replay": False,
    }
    for key, want in expected.items():
        if body.get(key) != want:
            raise SmokeError(f"response.{key} = {body.get(key)!r}, expected {want!r}")
    txn_ids = body.get("transaction_ids")
    if not isinstance(txn_ids, list) or not txn_ids:
        raise SmokeError(f"response.transaction_ids missing/empty: {txn_ids!r}")
    log("API response body matches expected COD math")


def assert_persisted_outcome(dsn: str) -> None:
    # 1) order created + settled (delivered -> completed), still flagged COD.
    order = psql(dsn, f"SELECT status FROM public.orders WHERE id = '{ORDER_ID}' AND cod = true;")
    if order != ["completed"]:
        raise SmokeError(f"order not settled to completed (cod=true): {order!r}")
    log("order settled: delivered -> completed (cod=true)")

    # 2) audit entry with transaction-local actor/note context (0014 trigger).
    events = psql(
        dsn,
        "SELECT actor::text, from_status, to_status, coalesce(note, '') "
        f"FROM public.order_events WHERE order_id = '{ORDER_ID}' ORDER BY created_at;",
    )
    if len(events) != 1:
        raise SmokeError(f"expected exactly 1 audit event, got {len(events)}: {events!r}")
    actor, from_status, to_status, note = events[0].split("|", 3)
    if (actor, from_status, to_status) != (SYSTEM_ACTOR_ID, "delivered", "completed"):
        raise SmokeError(f"audit actor/status wrong: {events[0]!r}")
    if note != COD_NOTE:
        raise SmokeError(
            f"audit note did not round-trip through the transaction-local GUC: {note!r} "
            f"(expected {COD_NOTE!r}) — the native adapter must set_config and UPDATE in "
            "one transaction so the trigger sees the note."
        )
    log("audit event carries transaction-local actor + note (GUC -> 0014 trigger)")

    # 3) required ledger/commission entries, each double-entry balanced.
    txns = psql(
        dsn,
        "SELECT t.id::text, coalesce(sum(p.amount_ngwee), 0)::text "
        "FROM public.ledger_transactions t "
        "JOIN public.ledger_postings p ON p.transaction_id = t.id "
        f"WHERE t.order_id = '{ORDER_ID}' GROUP BY t.id;",
    )
    if len(txns) < 3:
        raise SmokeError(
            f"expected >=3 ledger transactions for the order, got {len(txns)}: {txns!r}"
        )
    for row in txns:
        _txn_id, total = row.split("|", 1)
        if int(total) != 0:
            raise SmokeError(f"ledger transaction not balanced (sum={total}): {row!r}")
    log(f"{len(txns)} ledger transactions posted, each double-entry balanced")

    balances = {
        "platform_cash": (PLATFORM_CASH_ID, COLLECTABLE_NGWEE),
        "commission_revenue": (COMMISSION_ID, -COMMISSION_NGWEE),
        "vendor_payable": (VENDOR_PAYABLE_ID, -NET_VENDOR_NGWEE),
        "cod_receivable": (COD_RECEIVABLE_ID, 0),
        "escrow": (ESCROW_ID, 0),
    }
    for label, (account_id, want) in balances.items():
        got = int(
            psql(
                dsn,
                "SELECT coalesce(sum(amount_ngwee), 0)::text FROM public.ledger_postings "
                f"WHERE account_id = '{account_id}';",
            )[0]
        )
        if got != want:
            raise SmokeError(f"{label} balance = {got} ngwee, expected {want}")
    log(
        "ledger balances correct: platform_cash +"
        f"{COLLECTABLE_NGWEE}, commission_revenue -{COMMISSION_NGWEE}, "
        f"vendor_payable -{NET_VENDOR_NGWEE}, cod_receivable 0"
    )

    # 4) order/escrow state consistent: escrow nets to zero (asserted above), order done.
    log("escrow nets to zero — order/escrow state consistent")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def main() -> int:
    dsn = os.environ.get("SUPABASE_DB_URL", DEFAULT_DSN)
    image = os.environ.get("VERGEO5_API_IMAGE", DEFAULT_IMAGE)
    base_url = f"http://127.0.0.1:{CONTAINER_PORT}"
    name = f"vergeo5-cod-smoke-{os.getpid()}"

    log(f"target Postgres: {dsn}")
    if _docker("version", check=False, capture=True).returncode != 0:
        raise SmokeError("Docker is not available — this smoke test drives the real image")

    server: ThreadingHTTPServer | None = None
    try:
        reset_and_apply_schema(dsn)
        seed_cod_scenario(dsn)
        ensure_image(image)

        server, auth = start_auth_stub()

        stop_container(name)  # clear any stale container from a previous run
        run_container(image, name, dsn, auth.supabase_url)
        wait_for_health(base_url, name)
        assert_no_psql_binary(name)

        body = drive_cod_confirmation(base_url, auth.token, name)
        assert_api_response(body)
        assert_persisted_outcome(dsn)

        log("PASS — production container drove the COD order end-to-end via the native adapter")
        return 0
    finally:
        stop_container(name)
        if server is not None:
            server.shutdown()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SmokeError as exc:
        log(f"FAIL — {exc}")
        sys.exit(1)
