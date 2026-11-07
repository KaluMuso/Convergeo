"""Actual RPC/constraints and two-session locks in an explicitly owned container.

No DSN fallback, schema reset, migration application or provider connection is
performed by this suite. Replay source beforehand in a network-none/tmpfs
container labelled convergeo.intake-atomic-test=true, then set
INTAKE_ATOMIC_TEST_CONTAINER to that container's name.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import time
import uuid
from collections.abc import Generator
from typing import Any, cast

import pytest

SIGNATURE = "public.insert_intake_class_a_listing(uuid,uuid,uuid,jsonb)"


class Database:
    def __init__(self, container: str) -> None:
        self.command = [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-XAtq",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "VERBOSITY=verbose",
        ]

    def run(self, sql: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(self.command, input=sql, text=True, capture_output=True, timeout=15)

    def scalar(self, sql: str) -> str:
        result = self.run(sql)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def session(self) -> subprocess.Popen[str]:
        return subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )


@pytest.fixture(scope="module")
def database() -> Database:
    container = os.environ.get("INTAKE_ATOMIC_TEST_CONTAINER")
    if not container:
        pytest.skip("explicit owned disposable intake test container was not supplied")
    inspected = subprocess.run(
        ["docker", "inspect", container], capture_output=True, text=True, check=True, timeout=10
    )
    info = json.loads(inspected.stdout)[0]
    assert info["Config"]["Labels"].get("convergeo.intake-atomic-test") == "true"
    assert info["HostConfig"]["NetworkMode"] == "none"
    assert "/var/lib/postgresql/data" in info["HostConfig"]["Tmpfs"]
    assert not info["HostConfig"].get("PortBindings")
    db = Database(container)
    assert db.scalar(f"select to_regprocedure('{SIGNATURE}') is not null;") == "t"
    return db


@pytest.fixture()
def case(database: Database) -> Generator[dict[str, Any], None, None]:
    ids = {
        k: str(uuid.uuid4()) for k in ("owner", "vendor", "product", "category", "other_category")
    }
    database.scalar(f"""
      insert into auth.users(id) values ('{ids["owner"]}');
      insert into public.vendors(id,owner_user_id,slug,display_name,status,kyc_tier)
        values ('{ids["vendor"]}','{ids["owner"]}',
                'atomic-{ids["vendor"]}','Local vendor','active',2);
      insert into public.categories(id,name,slug,path,commission_key) values
        ('{ids["category"]}','Local catalog','atomic-{ids["category"]}','atomic','default'),
        ('{ids["other_category"]}','Other catalog',
         'atomic-{ids["other_category"]}','atomic','default');
      insert into public.products(id,name,slug,category_id,status,product_class,
        sale_unit,base_unit,base_units_per_sale_unit_milli) values
        ('{ids["product"]}','Local product','atomic-{ids["product"]}','{ids["category"]}',
         'active','A','each','each',1000);
    """)
    yield ids
    # Fixtures are only in this disposable container; preserve failed-run state
    # until its owner removes it, avoiding broad cleanup against any database.


def payload(case: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    row = {
        "vendor_id": case["vendor"],
        "product_id": case["product"],
        "title_override": "Local product",
        "price_ngwee": 350_000,
        "compare_at_ngwee": None,
        "product_class": "A",
        "condition": "new",
        "condition_detail": "new",
        "sale_unit": "each",
        "unit_step_milli": 1000,
        "min_steps": 1,
        "fulfilment_mode": "stocked",
        "lead_time_days": None,
        "vendor_capacity_per_week": None,
        "defect_notes": None,
        "stock_mode": "always_available",
        "stock_qty": None,
        "wholesale": False,
        "price_tiers": None,
        "moq": 1,
        "returnable": False,
        "return_window_hours": None,
        "status": "draft",
    }
    return dict(row, **overrides)


def rpc(case: dict[str, Any], row: Any, *, role: str = "service_role") -> str:
    serialized = json.dumps(row).replace("'", "''")
    return f"""set role {role};
      select row_to_json(r) from public.insert_intake_class_a_listing(
        '{case["vendor"]}', '{case["product"]}', '{case["category"]}', '{serialized}'::jsonb) r;
    """


def no_listing(database: Database, case: dict[str, Any]) -> None:
    assert (
        database.scalar(
            f"select count(*) from public.vendor_listings where vendor_id='{case['vendor']}';"
        )
        == "0"
    )


def test_privileges_invoker_and_empty_search_path(database: Database) -> None:
    for role in ("anon", "authenticated"):
        assert (
            database.scalar(f"select has_function_privilege('{role}','{SIGNATURE}','execute');")
            == "f"
        )
    assert (
        database.scalar(f"select has_function_privilege('service_role','{SIGNATURE}','execute');")
        == "t"
    )
    assert (
        database.scalar(f"select prosecdef from pg_proc where oid='{SIGNATURE}'::regprocedure;")
        == "f"
    )
    assert (
        database.scalar(
            f"select proconfig = array['search_path=\"\"'] "
            f"from pg_proc where oid='{SIGNATURE}'::regprocedure;"
        )
        == "t"
    )
    assert (
        database.scalar(f"""select count(*) from pg_proc p, lateral aclexplode(p.proacl) acl
      where p.oid='{SIGNATURE}'::regprocedure
        and acl.grantee=0 and acl.privilege_type='EXECUTE';""")
        == "0"
    )


@pytest.mark.parametrize("role", ["anon", "authenticated", "postgres"])
def test_other_roles_cannot_invoke(database: Database, case: dict[str, Any], role: str) -> None:
    result = database.run(rpc(case, payload(case), role=role))
    assert result.returncode != 0 and "42501" in result.stderr, result.stderr
    no_listing(database, case)


@pytest.mark.parametrize("row", [None, [], "payload", 123])
def test_payload_must_be_an_object(database: Database, case: dict[str, Any], row: Any) -> None:
    result = database.run(rpc(case, row))
    assert result.returncode != 0 and "22023" in result.stderr
    no_listing(database, case)


@pytest.mark.parametrize("argument", ["vendor", "product", "category"])
def test_null_rpc_identity_is_rejected(
    database: Database, case: dict[str, Any], argument: str
) -> None:
    sql = rpc(case, payload(case)).replace(f"'{case[argument]}'", "null", 1)
    result = database.run(sql)
    assert result.returncode != 0 and "22023" in result.stderr
    no_listing(database, case)


@pytest.mark.parametrize("field", ["vendor_id", "product_id"])
def test_valid_but_mismatched_payload_identity_is_rejected(
    database: Database, case: dict[str, Any], field: str
) -> None:
    result = database.run(rpc(case, payload(case, **{field: str(uuid.uuid4())})))
    assert result.returncode != 0 and "22023" in result.stderr
    no_listing(database, case)


def test_tracked_stock_description_and_exact_large_integer_money(
    database: Database, case: dict[str, Any]
) -> None:
    receipt = json.loads(
        database.scalar(
            rpc(
                case,
                payload(
                    case,
                    stock_mode="tracked",
                    stock_qty=4,
                    description="Vendor's exact café description",
                    price_ngwee=9_007_199_254_740_993,
                ),
            )
        )
    )
    assert (
        database.scalar(
            "select stock_qty::text||'|'||price_ngwee::text||'|'||description "
            f"from public.vendor_listings where id='{receipt['id']}';"
        )
        == "4|9007199254740993|Vendor's exact café description"
    )


def test_caller_search_path_cannot_shadow_canonical_tables(
    database: Database, case: dict[str, Any]
) -> None:
    result = database.run(
        "create temp table products(id uuid); create temp table categories(id uuid); "
        "set search_path=pg_temp; " + rpc(case, payload(case))
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["product_id"] == case["product"]


@pytest.mark.parametrize("condition", ["new", "refurbished"])
def test_real_shared_creation_payload(
    database: Database, case: dict[str, Any], condition: str
) -> None:
    from types import SimpleNamespace

    from app.routers.vendor_listings import create_listing_for_vendor
    from app.services.intake.handoff import build_listing_request
    from tests.test_listing_create import FakeSupabaseClient, _seed_base

    fake = FakeSupabaseClient()
    _seed_base(fake, kyc_tier=2)
    vendor = fake.tables["vendors"].rows[0]
    vendor["id"] = case["vendor"]
    fake.tables["products"].rows[0]["id"] = case["product"]
    fake.tables["products"].rows[0]["categories"] = {"commission_key": "default"}

    def insert(row: dict[str, Any]) -> dict[str, Any]:
        receipt = json.loads(database.scalar(rpc(case, row)))
        assert receipt["status"] == "draft" and receipt["product_id"] == case["product"]
        return cast(dict[str, Any], receipt)

    created = create_listing_for_vendor(
        SimpleNamespace(client=fake),
        vendor=vendor,
        body=build_listing_request(
            {"title": "Local product", "price_ngwee": 350_000, "condition": condition},
            product_id=case["product"],
        ),
        insert_listing=insert,
    )
    assert (
        database.scalar(
            "select condition||'|'||condition_detail||'|'||price_ngwee::text||'|'||status "
            f"from public.vendor_listings where id='{created.listing_id}';"
        )
        == f"{condition}|{condition}|350000|draft"
    )
    assert not fake.tables["vendor_listings"].rows


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "12345678-1234-4234-8234-123456789abc"),
        ("created_at", "2026-10-11"),
        ("category_id", None),
        ("product_variant_id", None),
        ("description", {}),
        ("vendor_id", None),
        ("product_id", None),
        ("vendor_id", "bad"),
        ("status", "active"),
        ("status", None),
        ("product_class", "B"),
        ("condition", None),
        ("condition", "used"),
        ("condition_detail", None),
        ("condition_detail", "refurbished"),
        ("sale_unit", "kg"),
        ("unit_step_milli", 500),
        ("unit_step_milli", None),
        ("min_steps", 2),
        ("price_ngwee", "350000"),
        ("price_ngwee", True),
        ("price_ngwee", 0),
        ("price_ngwee", 350000.5),
        ("price_ngwee", None),
        ("price_ngwee", 2**63),
        ("stock_qty", "4"),
        ("stock_qty", 4),
        ("stock_mode", "tracked"),
        ("wholesale", "false"),
        ("wholesale", True),
        ("returnable", None),
        ("fulfilment_mode", "made_to_order"),
        ("price_tiers", []),
        ("compare_at_ngwee", 400000),
        ("lead_time_days", 1),
        ("title_override", " "),
    ],
)
def test_untrusted_payload_rejected_without_write(
    database: Database, case: dict[str, Any], field: str, value: Any
) -> None:
    result = database.run(rpc(case, payload(case, **{field: value})))
    assert result.returncode != 0, result.stdout
    no_listing(database, case)


@pytest.mark.parametrize(
    "field",
    [
        "vendor_id",
        "product_id",
        "condition",
        "condition_detail",
        "status",
        "price_ngwee",
        "stock_qty",
    ],
)
def test_missing_required_values_rejected(
    database: Database, case: dict[str, Any], field: str
) -> None:
    row = payload(case)
    del row[field]
    result = database.run(rpc(case, row))
    assert result.returncode != 0 and "22023" in result.stderr
    no_listing(database, case)


def test_constraint_failure_rolls_back_entire_transaction(
    database: Database, case: dict[str, Any]
) -> None:
    sql = "begin;" + rpc(case, payload(case)) + rpc(case, payload(case, price_ngwee=0)) + "commit;"
    result = database.run(sql)
    assert result.returncode != 0 and "23514" in result.stderr
    no_listing(database, case)


def send(session: subprocess.Popen[str], sql: str) -> None:
    assert session.stdin
    session.stdin.write(sql + "\n")
    session.stdin.flush()


def marker(session: subprocess.Popen[str], expected: str) -> None:
    assert session.stdout
    deadline = time.monotonic() + 10
    received = ""
    while time.monotonic() < deadline:
        ready, _, _ = select.select([session.stdout], [], [], 0.1)
        if ready:
            chunk = os.read(session.stdout.fileno(), 65536).decode()
            received += chunk
            if expected in received.splitlines():
                return
            assert chunk or session.poll() is None, f"session exited before {expected}"
    pytest.fail(f"session did not reach {expected}")


def wait_for_block(database: Database, application: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = database.scalar(
            f"select count(*) from pg_stat_activity where application_name='{application}' "
            "and wait_event_type='Lock' and cardinality(pg_blocking_pids(pid))>0;"
        )
        if state == "1":
            return
        time.sleep(0.02)
    pytest.fail("did not witness the second database session blocked by a row lock")


@pytest.mark.parametrize(
    "change,reason",
    [
        ("product_class='B'", "intake_canonical_class"),
        ("sale_unit='kg'", "intake_canonical_units"),
        ("status='pending_moderation'", "intake_canonical_unavailable"),
        ("category_id", "intake_canonical_category"),
        ("category_prohibited", "intake_canonical_category"),
    ],
)
def test_rpc_waits_for_writer_and_revalidates_committed_values(
    database: Database, case: dict[str, Any], change: str, reason: str
) -> None:
    owner = database.session()
    waiter = database.session()
    application = "intake_wait_" + uuid.uuid4().hex
    if change == "category_prohibited":
        update = f"update public.categories set prohibited=true where id='{case['category']}';"
    else:
        assignment = (
            f"category_id='{case['other_category']}'" if change == "category_id" else change
        )
        update = f"update public.products set {assignment} where id='{case['product']}';"
    try:
        send(owner, "begin;" + update + "\n\\echo WRITER_HELD")
        marker(owner, "WRITER_HELD")
        send(waiter, f"set application_name='{application}';" + rpc(case, payload(case)))
        wait_for_block(database, application)
        send(owner, "commit;\n\\q")
        owner.communicate(timeout=10)
        stdout, stderr = waiter.communicate(timeout=10)
        assert waiter.returncode != 0 and "23514" in stderr and reason in stderr, (stdout, stderr)
        no_listing(database, case)
    finally:
        for session in (owner, waiter):
            if session.poll() is None:
                session.kill()
            session.communicate()


@pytest.mark.parametrize("target", ["product", "category"])
def test_rpc_holds_relationship_locks_until_commit(
    database: Database, case: dict[str, Any], target: str
) -> None:
    owner = database.session()
    waiter = database.session()
    application = "intake_update_" + uuid.uuid4().hex
    update = (
        f"update public.products set product_class='B',sale_unit='kg' where id='{case['product']}';"
        if target == "product"
        else f"update public.categories set prohibited=true where id='{case['category']}';"
    )
    try:
        send(owner, "begin;" + rpc(case, payload(case)) + "\n\\echo INSERT_HELD")
        marker(owner, "INSERT_HELD")
        send(waiter, f"set application_name='{application}';" + update + "\n\\q")
        wait_for_block(database, application)
        # A separate reader cannot observe an uncommitted listing.
        no_listing(database, case)
        send(owner, "commit;\n\\q")
        owner.communicate(timeout=10)
        stdout, stderr = waiter.communicate(timeout=10)
        assert waiter.returncode == 0, (stdout, stderr)
        assert (
            database.scalar(
                "select count(*) from public.vendor_listings "
                f"where vendor_id='{case['vendor']}' and status='draft';"
            )
            == "1"
        )
    finally:
        for session in (owner, waiter):
            if session.poll() is None:
                session.kill()
            session.communicate()
