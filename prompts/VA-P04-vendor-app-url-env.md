> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VA-P04 — Set vendor-app URL env `[OPS]`

## 1. Context
**Wave 1.** Source: `01-audit-findings.md` DL-6; MR-C01; critical-risk R1; `release-gates.md` G10. **Depends on VA-P01** (promotion first, so the redeploy carries the tip). **Live (07-18/07-19):** customer `/en/sell` shows **disabled** seller CTAs — "Vendor signup is temporarily unavailable" — because `NEXT_PUBLIC_VENDOR_APP_URL` is unset in the customer production build; the code is **fail-closed** (no `localhost:3001` leak, verified), so the fix is purely the env var. The vendor app itself is live at `vendor.vergeo5.com`.
**Type:** `[OPS]` — Cursor writes the evidence doc; the **founder** sets the Vercel env and redeploys `convergeo-customer`. No application code (already fail-closed).

## 2. Objective & scope
Set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on the customer Vercel project, redeploy, and verify the seller CTA now links to the vendor app.
**Non-goals:** any code change (the `vendor-app.ts` fail-closed logic stays); enabling money flags; touching vendor/admin projects.

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/cta.md`
**Guardrail: modify ONLY this file.**

## 4. Implementation spec (runbook)
- On Vercel project `convergeo-customer` (`prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP`): set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` for the **Production** environment (and Preview if desired).
- Redeploy production (a `NEXT_PUBLIC_*` var is inlined at build → a rebuild is required; do **not** just restart).
- Verify the `/en/sell` CTA href and copy.

## 9. Security
- Only a public `NEXT_PUBLIC_*` URL (no secret). Confirm no `localhost` string appears in the rendered `/en/sell` HTML.

## 10. Tests / verification (RUN before reporting)
```bash
curl -sS -m15 https://www.vergeo5.com/en/sell | grep -o 'https://vendor\.vergeo5\.com[^"]*' | head   # CTA href present
curl -sS -m15 https://www.vergeo5.com/en/sell | grep -c 'temporarily unavailable'   # expect 0
curl -sS -m15 https://www.vergeo5.com/en/sell | grep -c 'localhost'                  # expect 0
```

## 11. Acceptance criteria / DoD
- [ ] `/en/sell` seller CTA href = `https://vendor.vergeo5.com…`; CTA enabled.
- [ ] No "temporarily unavailable" copy; **no** `localhost` in the HTML.
- [ ] Env set on Production and a rebuild (not just restart) performed.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VA-P04 — Set vendor-app URL env
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the three grep results
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
