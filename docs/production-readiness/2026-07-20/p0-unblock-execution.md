# P0 unblock execution (2026-07-20 session)

**UTC start:** 2026-07-20T15:49Z  
**Master tip at start:** `bbe964e` (later advanced by merges)  
**Constraint:** `public_launch` unchanged · no production Lenco charges · money n8n stays unpublished until API+F9b green.

---

## Live fingerprint (re-probed)

| Surface                               | Result                                                                                    |
| ------------------------------------- | ----------------------------------------------------------------------------------------- |
| `GET https://api.vergeo5.com/healthz` | **502** (Caddy upstream down)                                                             |
| `GET https://api.vergeo5.com/readyz`  | **502**                                                                                   |
| DNS `api.vergeo5.com`                 | `91.107.236.37` (Hetzner)                                                                 |
| SSH `root@91.107.236.37`              | **Permission denied (publickey)** from this agent                                         |
| Customer `/en/health`                 | **200** `buildId=cde40bf…` (prod)                                                         |
| Vendor `/en/health`                   | **307** (locale redirect; app up)                                                         |
| Admin                                 | Access-gated **302**                                                                      |
| Supabase `dpadrlxukcjbewpqympu`       | **ACTIVE_HEALTHY**                                                                        |
| n8n MCP workflows                     | **3** total, **0 active** (dispatch, reconciliation, shared error alert)                  |
| n8n Header Auth creds                 | Dispatch / Reconciliation / Payment Sweeper only (missing Release/Tickets/Order/Backup/…) |
| Sentry org `convergeo-w2`             | Team `convergeo` exists; **no** Vergeo5 projects (create API errored)                     |
| Vercel customer prod                  | `dpl_6Pgevsi…` @ `cde40bf` (behind master)                                                |
| Money rows                            | `orders=payments=refunds=0`                                                               |

---

## Execution status by P0 item

### 1. API 502 (G1) — **BLOCKED_EXTERNAL**

Caddy answers 502 ⇒ container not listening on `127.0.0.1:8000` (or stopped). This agent has no Hetzner SSH key.

**Founder action (highest leverage):** on the API host run:

```bash
# On 91.107.236.37 — inspect
docker ps -a --filter name=vergeo5-api
curl -sS -m 2 http://127.0.0.1:8000/healthz || true
journalctl -u caddy -n 50 --no-pager || true

# Redeploy from GHCR (uses host env file — never print secrets)
sudo bash /path/to/infra/redeploy-api.sh latest
# or: copy repo infra/redeploy-api.sh then:
# IMAGE_TAG=<git-sha> sudo bash infra/redeploy-api.sh
```

**Optional:** add this agent SSH public key to `root` (or deploy user) authorized_keys so the next cloud run can finish G1:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPONzexoi+CLIwY4Xi8icTYKJTXkVggy12HTc2wk4s4s cursor-cloud-agent-vergeo5
```

**Done when:** `curl -fsS https://api.vergeo5.com/healthz` and `/readyz` both 200; record image digest + git SHA.

---

### 2. Migration tip hygiene — **DONE (live)**

| Step                                 | Status                                                                              |
| ------------------------------------ | ----------------------------------------------------------------------------------- |
| RC-02 reconcile PR #387              | **Merged** — repo `0063`=revoke (matches live), `0064` FORCE RLS, `0065` source_key |
| Apply `0064_force_rls_launch_tables` | **Applied** `20260720155653` — FORCE=true on three launch tables                    |
| Apply `0065_refunds_source_key_uniq` | **Applied** `20260720155702` — `refunds.source_key` present                         |
| Live tip                             | **`0065_refunds_source_key_uniq`**                                                  |

Precondition satisfied for this apply: money tables empty; DDL additive/reversible; Supabase project healthy.

---

### 3. Promote frontend SHAs (G9) — **HOLD** until API 200

| App      | Prod SHA                   | Intentional promote tip           | Action                                                            |
| -------- | -------------------------- | --------------------------------- | ----------------------------------------------------------------- |
| customer | `cde40bf`                  | `origin/master` after API healthy | **Do not promote** while API 502 (widens broken catalogue/search) |
| vendor   | `5a4668a` (prior evidence) | master tip                        | Hold                                                              |
| admin    | `2f99711` (prior evidence) | master tip                        | Hold / low risk after API                                         |

Rollback candidates remain on Vercel (`isRollbackCandidate` for customer prod `dpl_6Pgevsi…`).

---

### 4. n8n fleet (DEP-02 / S4) — **PARTIAL / BLOCKED**

- Repo JSON: 20 files under `infra/n8n/` (incl. `backup.json`).
- Live: 3 inactive workflows; money ticks correctly unpublished.
- Creds missing for Release / Tickets / Order Jobs / Backup / Digests / etc.
- MCP cannot raw-import committed JSON; SDK rewrite required per workflow.

**Next (after API 200):**

1. Founder creates remaining HTTP Header Auth credentials (names in `n8n-fleet-import-verify.md` §7).
2. Import registry JSON via n8n UI **or** SDK recreate — bind creds — leave **unpublished**.
3. Manual tick success on non-money first (`notification-dispatch`, `backup` watchdog once OCI ready).
4. Activate money ticks only after F9b sandbox drills.

---

### 5. F9b + sandbox money (S1/S2) — **BLOCKED_EXTERNAL**

Needs: API 200 + founder `LENCO_*` sandbox token/account/public key in API env. Agent has no Lenco secrets. Do not run real charges.

---

### 6. Sentry + uptime (G6 / LIVE-08) — **BLOCKED_EXTERNAL**

- Org `convergeo-w2` / team `convergeo` OK.
- `create_project` for `vergeo5-api` / `vergeo5-customer` failed (Sentry API event IDs `ae4dfd52…`, `7a1903bf…`).
- Code paths already on master (#378); need DSNs in Vercel/API env + one authenticated test-event + uptime alert fire.

**Founder:** create projects in Sentry UI (or fix MCP token scopes) → paste DSNs → re-run Prompt 9 live evidence.

---

### 7. Backup + restore / rollback (G7/G9) — **NOT_RUN** (ops)

- `#374` backup artifacts on master (CODE_COMPLETE).
- Still need: OCI Object Storage dated dump + ≤30‑min restore drill; controlled frontend rollback after intentional promote.
- Blocked by: no OCI CLI/SSH in agent; API digest unknown while 502.

---

## P1 / P2 / P3 sequencing (this programme)

| Track                          | Status      | Gate                                                  |
| ------------------------------ | ----------- | ----------------------------------------------------- |
| P1 browse-beta discovery prove | Wait        | API 200 + optional customer promote with demo-exclude |
| P1 #372 security CI / #370 E2E | Open drafts | Review after API; #372 had conflicts                  |
| P2 #371/#373/#382 UX           | Open drafts | Do not merge over broken API                          |
| P3 CCP-01 zh switcher          | PR #386     | Mergable now (no API dep)                             |
| P3 CCP-06/08 …                 | Pending     | Parallel after CCP-01                                 |
| Founder F4 / F9a / F9b         | External    | No `public_launch` flip                               |

---

## Questions for founder (blocking G1+)

1. **API host:** Can you redeploy with `infra/redeploy-api.sh` **or** install the agent SSH pubkey above?
2. **Lenco F9b:** Provide sandbox `LENCO_API_TOKEN` / account / public key into the API host env (not chat)?
3. **n8n:** Confirm remaining Header Auth credentials + `$env.API_URL` / internal tokens on the n8n host?
4. **Sentry:** Create `vergeo5-api` + three Next apps in org `convergeo-w2` (MCP create failed) and share DSNs via Vercel/env?
5. **Backup:** Confirm Supabase PITR/daily backup retention **or** run one OCI dump so G7 can clear?

---

## Recommendation

1. Founder restores API → 200 (minutes).
2. Agent then: fingerprint digest · promote frontends intentionally · import/activate non-money n8n · sandbox money drill · Sentry test-event · backup restore.
3. Keep `public_launch=false`.
