> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VA-P01 — Promote frontends to master tip `[OPS]`

## 1. Context
**Wave 1.** Source: `docs/production-readiness/2026-07-19/vision-audit/01-audit-findings.md` DL-1/DL-2; `03-waves-and-phases.md` (VM-A). Closes **G1** (route integrity) + **G17** (panel honesty PRODUCTION_VERIFIED). **Depends on Wave-0 decision B-1** (release strategy: `02-open-questions.md`).
**Live drift (2026-07-19, verified):** customer production Vercel deploy `dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW` = commit **`cc4a824`** (#296). `/en|fr|zh/categories` return **HTTP 500** (digest `3012388270`) because the #298 client-boundary fix — and #302 live-beta work — are on `master` but **never promoted to production** (newer Vercel builds are `target:null` previews). Vendor/admin production SHA last VERIFIED `8cc1fa0` (07-18) and not re-confirmed.
**Type:** `[OPS]` — Cursor writes the evidence doc + probe script; the **founder promotes** on Vercel (team `vergeo-projects` / `team_I2OEqmMjTwN2k5g7ACbQW705`).

## 2. Objective & scope
Bring all three customer/vendor/admin production aliases to the current `master` tip (per B-1, optionally merging #302 first), record the promoted deployment ids + commit SHAs, and re-probe the previously-broken routes.
**Non-goals:** enabling any money flag or `public_launch` (stays false); setting `NEXT_PUBLIC_VENDOR_APP_URL` (VA-P04); any application code.

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/deploy-promote.md`
- `scripts/ops/probe-frontends.sh` (curl probe set; idempotent, read-only)
**Guardrail: modify ONLY these files; anything else → DEVIATIONS.**

## 4. Implementation spec (runbook the founder executes)
- **Per B-1:** if live-beta is chosen, merge PR #302 to `master` first; then promote. Otherwise promote the current `master` tip.
- For each Vercel project — `convergeo-customer` (`prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP`), `convergeo-vendor` (`prj_QiX9rpStSpNeEXd3UZDFFp7H2dXf`), `convergeo-admin` (`prj_Bpf852KXDuG1NZUomri0OsMBt1YS`): promote/redeploy a **production** deployment built from the tip; record `dpl_…` id, `meta.githubCommitSha`, and production aliases.
- Confirm production aliases (`www.vergeo5.com`/`vergeo5.com`) point at the new deployment id.

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A (deployment only). Do not change route code — if categories still 500 **after** the tip is live, that is a code regression → DEVIATIONS + stop.

## 9. Security
- No env-var values printed; no secrets in the evidence doc. Confirm admin origin still Cloudflare-Access-gated after promotion.

## 10. Tests / verification (RUN before reporting) — `scripts/ops/probe-frontends.sh`
```bash
curl -sS -m 15 https://www.vergeo5.com/en/health          # {"status":"ok","app":"customer"}
for l in en fr zh; do curl -sS -m15 -o /dev/null -w "$l %{http_code}\n" https://www.vergeo5.com/$l/categories; done  # expect 200 (not 500/digest 3012388270)
curl -sS -m15 -o /dev/null -w "vendor %{http_code}\n" https://vendor.vergeo5.com/en/health   # auth-gated redirect
curl -sS -m15 -o /dev/null -w "admin %{http_code}\n"  https://admin.vergeo5.com/en/health    # CF Access challenge
curl -sS -m 15 https://api.vergeo5.com/healthz
```

## 11. Acceptance criteria / DoD
- [ ] 3 production deployment SHAs == current `master` tip (recorded with `dpl_…` ids).
- [ ] `/en|fr|zh/categories` → **200** (populated, honest `categories-empty*`, or honest `categories-unavailable-*` — **not** digest `3012388270`).
- [ ] Vendor/admin health gated as expected; API health 200.
- [ ] `public_launch` and money flags **unchanged (false)**.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VA-P01 — Promote frontends to master tip
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the probe output (3× categories codes, health)
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
