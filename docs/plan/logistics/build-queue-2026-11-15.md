# Build queue — Sun 15 Nov 2026 (founder requests 07:34) — start after 10:00 weekly reset

Agents: ≤4 rolling; sonnet for UI/copy, opus for money/authz/data-model, haiku for checks/audits.

## W1 Multi-branch businesses (opus, data model + authz)
- Business (legal entity; owner KYC once; PACRA cert for registered companies) → Branches/Shops (each = own storefront, slug, location+GPS+landmark+map, contacts, hours, payout MoMo, listings, plan/subscription billed separately).
- Anti-duplication: PACRA number unique per legal entity; branch GPS must be ≥ N m from sibling branches; storefront photo + proof of premises (lease/utility/business permit) for physical branches; MoMo payout number unique across owners (founder rule: no duplicate MoMo); fuzzy dedup on name/phone/photos/GPS → admin review queue; unregistered market traders (no PACRA) limited to 1 shop.
- Admin: branch verification queue; per-branch plan; audit.
- Flag `multi_branch` default off.

## W2 Vendor listing fixes (sonnet) — and sweep platform for same pattern
- Quick list 422 vague "publishing" error on Save draft → field-level errors; draft never blocked by publish policy.
- Condition forced "Used" for Class D (new T-shirt) → allow New; audit every class/condition rule.
- Delivery/pickup choice on listing create/edit (+ services/events where relevant).
- Deleted (removed) listing edit page still opens → show removed state.
- Wording: one name for verification; human shop slug from business name (no draft-xxxx); one "Create listing" button; scanner camera-blocked → lead with PIN; add Settings menu.
- Onboarding: Back + Save & continue later on every step; profile page revisit.

## W3 Events (sonnet)
- Non-organiser: "Become an organiser" instead of load error.
- Collaboration: vendor requests to run an event under a verified organiser; organiser approves; organiser readiness checklist (scanner device, staff, venue contract). Flag-gated.

## W4 Admin UX (sonnet)
- Navbar shows signed-in admin name, email, role (superadmin/admin/…).
- Sidebar sticky with own scroll; keep scroll position across navigation (no jump to top).
- Tighten whitespace/gaps on vendor + admin pages; consistent density tokens.
- Release path for #787 (vendors list/edit, audit log, roles) and #797 (analytics).

## W5 Customer fixes (sonnet)
- Email as default sign-in while OTP off; COD-only copy; /sell invite link; search "no results" + hide test event tiers (needs founder yes); empty-cart checkout guard; /browse 404; social links; "Vergeo5"→Convergeo; made-to-order "ready within a week" label; KYC 500→404; first-approve failure.

## W6 Stack review (haiku audit → sonnet implement)
- Founder supplied notes on Next.js 16.x, Tailwind 4.3, FastAPI 0.16x features. FIRST verify versions/claims against official release notes; apply security patches immediately.
- Adopt within current majors now (Tailwind container queries, has-/user-invalid, scrollbar & tabular-nums, motion-safe; FastAPI param models, router-level deps, native OpenTelemetry, SSE for live order feed, OpenAPI→TS client).
- Next 15→16 (proxy.ts, Cache Components, updateTag) = separate upgrade branch with full CI + bundle/Lighthouse gates; not mixed with feature work.

## 08:01 founder decisions
- Multi-branch: branches of the SAME verified owner may share one MoMo payout number, subject to admin review; different owners never share.
- Events: non-organiser sees "Become an organiser" OR "Run an event with a verified organiser" (approved).
- Pricing: add Chain/Enterprise tiers for large retailers (Shoprite, Game, Woolworths, Home Essentials) up to ~K7,500/mo; branches are a paid add-on on lower tiers. Admin-editable (builds on vendor_plans, #798).
- W7 Customer app redesign (sonnet): denser, marketplace-grade layout inspired by Alibaba/Amazon/eBay/Takealot references — compact sticky header with prominent search, category tiles grid, deal/discount rails, trust strip, product cards with price + discount badge + rating, back-to-top, reduced whitespace; keep ≤150 KB route budget and 3G performance.
- Models: sonnet default; haiku for checks/audits; opus (low/medium effort) for money/authz/data-model; fable only for hardest tasks.
