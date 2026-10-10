"""Prove the last-superadmin trigger serializes two concurrent removals.

Run only against a disposable local migration replay. The synthetic users are
left in that database, which the caller must destroy after this check.
"""

from __future__ import annotations

import os
import threading
import time
from urllib.parse import urlparse
from uuid import uuid4

import psycopg


def main() -> None:
    url = os.environ.get("SUPABASE_DB_URL", "")
    parsed = urlparse(url)
    if (
        os.environ.get("CONVERGEO_DISPOSABLE_DB") != "1"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.path != "/postgres"
    ):
        raise RuntimeError("A disposable local postgres database is required")

    first_id, second_id = str(uuid4()), str(uuid4())
    with psycopg.connect(url, autocommit=True) as setup:
        count = setup.execute(
            "select count(*) from public.user_roles where role = 'superadmin'"
        ).fetchone()
        assert count == (0,), "Replay database must have no superadmin assignments"
        for user_id in (first_id, second_id):
            setup.execute("insert into auth.users(id) values (%s)", (user_id,))
            setup.execute(
                "insert into public.profiles(id) values (%s) on conflict do nothing",
                (user_id,),
            )
            setup.execute(
                "insert into public.user_roles(user_id, role) values (%s, 'superadmin')",
                (user_id,),
            )

    second_started = threading.Event()
    result: dict[str, str | int] = {}

    def remove_second() -> None:
        with psycopg.connect(url) as connection:
            result["second_pid"] = connection.info.backend_pid
            second_started.set()
            try:
                connection.execute(
                    "delete from public.user_roles where user_id = %s and role = 'superadmin'",
                    (second_id,),
                )
                connection.commit()
                result["second"] = "committed"
            except psycopg.Error as exc:
                result["second"] = exc.sqlstate or "unknown"
                connection.rollback()

    with psycopg.connect(url) as first, psycopg.connect(url, autocommit=True) as observer:
        first.execute(
            "delete from public.user_roles where user_id = %s and role = 'superadmin'",
            (first_id,),
        )
        first_pid = first.info.backend_pid
        held = observer.execute(
            """select exists (
                select 1 from pg_catalog.pg_locks
                where pid = %s and locktype = 'advisory'
                  and classid = 724 and objid = 1 and objsubid = 2 and granted
            )""",
            (first_pid,),
        ).fetchone()
        assert held == (True,), "First removal did not hold advisory lock (724, 1)"

        thread = threading.Thread(target=remove_second, daemon=True)
        thread.start()
        try:
            assert second_started.wait(5), "Second connection did not start"
            second_pid = result["second_pid"]
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                # A live thread alone could be delayed before issuing its DELETE.
                # Inspect the exact ungranted advisory lock and its blocker in PG.
                row = observer.execute(
                    """select exists (
                        select 1
                        from pg_catalog.pg_locks as l
                        join pg_catalog.pg_stat_activity as activity using (pid)
                        where l.pid = %s and l.locktype = 'advisory'
                          and l.classid = 724 and l.objid = 1
                          and l.objsubid = 2 and not l.granted
                          and activity.wait_event_type = 'Lock'
                          and activity.wait_event = 'advisory'
                          and %s = any(pg_catalog.pg_blocking_pids(l.pid))
                    )""",
                    (second_pid, first_pid),
                ).fetchone()
                if row == (True,):
                    waiting = True
                    break
                if not thread.is_alive():
                    break
                time.sleep(0.05)
            assert waiting, (
                "Second removal was never observed waiting on advisory lock "
                f"(724, 1) held by backend {first_pid}; result={result}"
            )
            first.commit()
        finally:
            if first.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                first.rollback()
            thread.join(5)
        assert not thread.is_alive(), "Second removal did not finish after first committed"

    with psycopg.connect(url, autocommit=True) as check:
        remaining = check.execute(
            "select count(*) from public.user_roles where role = 'superadmin'"
        ).fetchone()
    assert result["second"] == "23514", result
    assert remaining == (1,), remaining
    print(
        f"PASS: backend {second_pid} waited on advisory lock (724, 1) "
        f"held by backend {first_pid}; "
        "concurrent removals leave one superadmin; second rejected with 23514"
    )


if __name__ == "__main__":
    main()
