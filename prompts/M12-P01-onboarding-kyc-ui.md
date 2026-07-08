> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **You solely own `vendor.json` this wave.**

# M12-P01 — Onboarding & KYC application UI

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master`:

- Vendor app: `apps/vendor/` is Next.js 15 + `localePrefix: "always"` + composed auth middleware (vendor-gated → `/{locale}/login`). **All routes live under `apps/vendor/app/[locale]/`** — the spec's `apps/vendor/app/onboarding/…` path is **stale (missing `[locale]`)**: create under **`apps/vendor/app/[locale]/onboarding/`**.
- `@vergeo/auth` (session/roles), `@vergeo/ui` (form primitives, deep imports), `@vergeo/i18n` available. Media/upload: Supabase Storage **private bucket** with the signing seam (M05-P10). Doc uploads (NRC/selfie) go to the private bucket via signed upload — reuse the existing media-signing endpoint; do NOT roll your own.
- **Interface edge with M12-P02 (same wave, KYC backend):** the KYC status machine + submit endpoints live in M12-P02 (`app/routers/kyc.py`). Code your UI against M12-P02's documented endpoint contract (draft→submitted→approved|rejected|resubmit; `kyc_records` + `vendors.kyc_tier`/`status`). If the contract is unclear, stub the calls behind a small client module + note in QUESTIONS; integration verified in Phase-4 review.
- i18n `vendor` namespace registered; `packages/i18n/messages/en/vendor.json` exists (has `pitch` from M12-P11). **Add an `onboarding` section, nested** (no flat dotted keys — next-intl nests on dots). You are the ONLY W6 pebble touching `vendor.json`.
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P01.

## 2. Objective & scope

Vendor onboarding: multi-step (business basics → T1 KYC: NRC photo + selfie capture + MoMo number for name-match → review/submit) + status screens, camera-first, resumable, private-bucket uploads.
**Non-goals:** no KYC backend/caps/status machine (M12-P02), no listing creation (M12-P03), no T2/PACRA flow beyond an entry point, no new deps/schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/onboarding/page.tsx` (multi-step) · `onboarding/status/page.tsx` · `onboarding/_components/*` (doc capture w/ camera, image-quality hints, step progress, review) · a small `onboarding/_lib/kyc-client.ts` (calls M12-P02 endpoints)
- **Modify:** `packages/i18n/messages/en/vendor.json` (add nested `onboarding` section; keep `pitch` + skeleton keys)
  **Guardrail: nothing else. No API routers (M12-P02), no schema/`db.ts`, no other app, no `request.ts`.**

## 4. Implementation spec

- **Multi-step flow:** business basics → T1 KYC (NRC photo + selfie **camera capture**, image-quality hints for mid-range Android; MoMo number for name-match) → review/submit. **Resumable** — persist per-step progress (localStorage + server draft via the KYC endpoint) so an interrupted flow resumes at the right step.
- **Uploads:** NRC/selfie → Supabase Storage **private bucket** via the signed-upload seam (RLS: only the vendor + admins can read). Never public.
- **Status screens:** pending / approved / rejected-with-reason / resubmit — rejected docs re-submittable **without restarting** the whole flow. T2 upgrade entry point (PACRA + company TPIN) as a stub link.
- **D9 gate:** nothing the vendor lists is public until approved (UI reflects this; enforcement is server-side in M12-P02).
- All copy via `vendor` namespace (`onboarding.*`); tokens only; one-handed at 360px.

## 5–8. UI/UX · Responsiveness · Performance · SEO

Camera-first, one-handed at 360px; resumable; light client JS; vendor app `noindex`.

## 9. Security

Docs to private bucket only (signed upload, RLS-scoped read); no service-role in the client; MoMo number handled as PII (not logged); no secrets.

## 10. Tests (RUN before reporting)

Component tests: **step persistence** (interrupted → resumes at step), **upload authz** (private-bucket path, signed), **resubmit** flow (rejected → re-upload without restart), status renders per state. i18n completeness for `vendor.onboarding.*` (nested, no flat keys). `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Full flow one-handed at 360px; interrupted flow resumes; rejected docs re-submittable without restart.
- [ ] Docs to private bucket (signed); nothing public until approved (UI).
- [ ] `vendor.json` `onboarding` nested; no schema/deps; repo green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M12-P01 — Onboarding & KYC application UI
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste step-persistence + upload-authz + resubmit + i18n output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none") — list the exact M12-P02 endpoint contract you assumed
