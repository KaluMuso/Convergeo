# API Deploy & Env-Safety Runbook

**Host:** `vergeo5-ubuntu-4gb-nbg1-2` (Hetzner, 4 GB) · **Container:** `vergeo5-api` (uvicorn, bind `127.0.0.1:8000`) · **Env file:** `/root/vergeo5-api.env`
**DB:** Supabase project `Vergeo5` (`dpadrlxukcjbewpqympu`, prod). **Written:** 2026-07-20 after the `ENV`-isolation deploy incident.

---

## 0. TL;DR safe live-beta config

```
ENV=production        # NOT "staging" — see §2
LENCO_ENV=sandbox     # no real money — see §3
public_launch=false   # feature flag (DB) — keeps checkout/collections gated
```

Change env → **re-run `redeploy-api.sh`** (a `restart` does NOT reload env — see §4). Verify:

```bash
docker exec vergeo5-api printenv | grep -E '^(ENV|LENCO_ENV)='
curl -fsS http://127.0.0.1:8000/healthz && curl -fsS https://api.vergeo5.com/healthz
```

---

## 1. Normal deploy

```bash
bash /root/redeploy-api.sh          # pulls :latest, recreates the container, waits for /healthz
docker ps --filter name=vergeo5-api # STATUS should read "(healthy)"
```

If `/healthz` doesn't go healthy in 30 s → `docker logs --tail 80 vergeo5-api`. `/healthz` has **no dependencies**, so a failure means the app crashed at startup (almost always env — §2) or the box is out of memory (§6), never a missing DB table.

---

## 2. The `ENV` staging-isolation guard (the crash we hit)

A recent image added a fail-closed guard: **`ENV=staging` refuses a production Supabase project ref**. Symptom in logs:

```
ValueError: ENV=staging refuses production Supabase project ref (dpadrlxukcjbewpqympu).
```

This VM points at the **production** Supabase project, so its env must be **`ENV=production`**. `ENV=staging` is only valid against a *separate* staging Supabase project (which does not exist yet). Do **not** set `ENV=staging` here.

---

## 3. `ENV` × `LENCO_ENV` money-safety matrix

`ENV` controls three staging-only suppressions; `LENCO_ENV` controls which Lenco endpoint is hit. **`LENCO_ENV` defaults to `production` if unset.**

| Config | App suppressions | Lenco | Meaning |
| ------ | ---------------- | ----- | ------- |
| `ENV=staging` + separate staging DB + `LENCO_ENV=sandbox` | outbound + payouts suppressed | sandbox | true isolated staging (needs a staging Supabase project) |
| **`ENV=production` + `LENCO_ENV=sandbox`** | none | sandbox | **current safe live-beta** — real app behavior, no real money |
| `ENV=production` + `LENCO_ENV=production` | none | **real** | **real-money launch** — only after legal sign-off + verification drills |

`ENV=production` **removes** the staging suppressions:
- `outbound_suppressed()` → **false** ⇒ WhatsApp/SMS/email send for real (creds are live).
- `payouts_suppressed()` → **false** ⇒ Lenco payouts execute if triggered.

So on this VM, keep `LENCO_ENV=sandbox` until you are deliberately going live. Never leave `ENV=production` + `LENCO_ENV=production` unless you intend real disbursements.

---

## 4. GOTCHA: `docker restart` does NOT reload `--env-file`

Env vars are baked into the container at **creation** (`docker run --env-file`). `docker restart` restarts the same process with the same vars. After editing `/root/vergeo5-api.env` you **must recreate** the container:

```bash
# WRONG — does not pick up env edits:
docker restart vergeo5-api
# (and `docker restart <IP>` just errors "No such container")

# RIGHT — recreates with the current env file:
bash /root/redeploy-api.sh
```

---

## 5. Pre-invite (before real beta users) checklist

- [ ] `ENV=production`, `LENCO_ENV=sandbox`, `public_launch=false` — verified via `printenv`.
- [ ] Internal cron endpoints reject a wrong token (fail-closed):
      `curl -s -o /dev/null -w '%{http_code}\n' -XPOST https://api.vergeo5.com/internal/stock-sweeper/tick -H 'X-Internal-Token: wrong'` → **401**.
- [ ] **Outbound**: SMS (Africa's Talking) + email (Resend) creds are LIVE and *not* env-suppressed in production. Keep the notification-dispatch n8n workflow off, or use test creds, until a sandbox send drill is done.
- [ ] n8n **payout / release** workflows stay OFF until a sandbox money drill passes.
- [ ] Secrets: never paste `/root/vergeo5-api.env` into chat/tickets; rotate anything exposed.

## 6. If the box is starved (4 GB VM shared with WAHA + zedcv-backend)

Symptom: container is `Killed`/exits with no traceback, or misses the 30 s health window under load.
`free -m` · `dmesg | grep -i oom` · `docker stats --no-stream`. Mitigate: bump the health-wait in `redeploy-api.sh`, add a `mem_limit`, or stop/limit noisy neighbors.

---

## 7. Database migrations

Live DB state (2026-07-20): applied through **`0063`**. `0057`–`0063` were applied via the Supabase MCP `apply_migration` (recorded with timestamp versions + `00NN_name`, matching how `0051`–`0056` were recorded).

**For future migrations against this project, use `supabase migration up` or the MCP `apply_migration` — NOT `supabase db push`.** `db push` matches by the filename-prefix version (`0057`), but `schema_migrations` stores timestamp versions for `0051`+, so `db push` would think they're unapplied and try to re-run them (and `0059`/`0062` have non-idempotent `create table` / `create unique index` that would then error).

The deployed image expects the DB to be at the same migration level it was built against — if you deploy a newer image, apply the new migrations **first** (or the money/refund/release/checkout paths that reference new DB objects will error at runtime).
