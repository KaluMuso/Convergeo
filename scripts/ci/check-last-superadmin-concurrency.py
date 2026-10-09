"""Prove the last-superadmin trigger serializes two concurrent removals.

Run only against a disposable local migration replay. The synthetic users are
left in that database, which the caller must destroy after this check.
"""

from __future__ import annotations

import os
import threading
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
    result: dict[str, str] = {}

    def remove_second() -> None:
        with psycopg.connect(url) as connection:
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

    with psycopg.connect(url) as first:
        first.execute(
            "delete from public.user_roles where user_id = %s and role = 'superadmin'",
            (first_id,),
        )
        thread = threading.Thread(target=remove_second, daemon=True)
        thread.start()
        assert second_started.wait(5), "Second removal did not start"
        thread.join(0.25)
        blocked = thread.is_alive()
        first.commit()
        thread.join(5)
        assert not thread.is_alive(), "Second removal did not finish after first committed"

    with psycopg.connect(url, autocommit=True) as check:
        remaining = check.execute(
            "select count(*) from public.user_roles where role = 'superadmin'"
        ).fetchone()
    assert blocked, "Concurrent removal did not wait for the advisory lock"
    assert result == {"second": "23514"}, result
    assert remaining == (1,), remaining
    print("PASS: concurrent removals leave one superadmin; second rejected with 23514")


if __name__ == "__main__":
    main()
