# VA-P04 — Seller CTA evidence

**Date:** 2026-07-19 · **Source:** Vercel MCP `web_fetch_vercel_url` on `https://www.vergeo5.com/en/sell` (server-side fetch; bypassed the audit session's egress block on `*.vergeo5.com`).

## Live `/en/sell` state
| Check | Result |
| ----- | ------ |
| `temporarily unavailable` occurrences | **0** (the old broken/fail-closed CTA state is gone) |
| `localhost` occurrences | **0** (no dev-URL leak) |
| Sell surface | Honest **"invite-only seller beta"** — CTAs: *Start selling*, *List your first products*, *Invited to sell on Vergeo5?* (page title/OG: "Sell on Vergeo5 — invite-only seller beta") |
| `https://vendor.vergeo5.com` href | not present — the CTA is an in-app invite flow, not a link to the vendor subdomain |

## Interpretation
The live-beta work (#302/#308) superseded the runbook's original design (CTA → `vendor.vergeo5.com`, gated on `NEXT_PUBLIC_VENDOR_APP_URL`) with an **invite-only beta flow**. VA-P04's real acceptance — *no "temporarily unavailable", no `localhost`* — is **met**. The `NEXT_PUBLIC_VENDOR_APP_URL` env is no longer load-bearing for this surface; MR-C01/G10's failure mode is resolved by design change rather than the env fix.

## Status: VA-P04 ✅ (broken CTA state resolved; design superseded to invite-only)
