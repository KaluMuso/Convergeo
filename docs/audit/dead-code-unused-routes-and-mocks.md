# Dead Code, Unused Routes & Mocks

---

## Unreachable routes (defined but not linked in UI)

### Customer

| Route                         | Issue                                 |
| ----------------------------- | ------------------------------------- |
| `/[locale]/calendar`          | Redirect to `/events?date_window=all` |
| `/[locale]/terms`, `/privacy` | Redirect to `/legal/*`                |
| `/[locale]/ui`                | `notFound()` in production            |
| `/[locale]/[...rest]`         | Intentional catch-all 404             |
| `/[locale]/(dev)/ui`          | Dev-only design preview               |

### Vendor (implemented, no primary nav)

| Route                         | Reachable via                              |
| ----------------------------- | ------------------------------------------ |
| `/analytics`                  | Direct URL only                            |
| `/scan`                       | Direct URL only                            |
| `/payouts`, `/payouts/method` | Direct URL only                            |
| `/reviews`                    | Direct URL only                            |
| `/returns`                    | Direct URL only                            |
| `/disputes`, `/disputes/[id]` | Internal links only                        |
| `/events/*` (entire subtree)  | Direct URL / sparse cross-links            |
| `/jobs`, `/jobs/[id]`         | Direct URL only                            |
| `/listings/import`            | Direct URL only                            |
| `/services/*`                 | Home quick-start (services archetype only) |

**Quick nav exposes only:** Home, Listings, Orders, Profile.

### Admin

| Item                                                | Issue                                      |
| --------------------------------------------------- | ------------------------------------------ |
| `OrphanedTierItem` type in `kyc/_components/api.ts` | Defined, never used — planned UI not built |

---

## Duplicate / alias routes

| Routes                            | Resolution         |
| --------------------------------- | ------------------ |
| `/terms` vs `/legal/terms`        | Permanent redirect |
| `/privacy` vs `/legal/privacy`    | Permanent redirect |
| Account wishlist vs shop wishlist | Possible overlap   |

---

## Mock data & stubs (production code paths)

| Item                                    | File                                      | Production behaviour                                        |
| --------------------------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| Demo listing detector                   | `(shop)/_components/demo-listing.ts`      | Badges Cloudinary `demo/` prefix; hidden in prod by default |
| Pickup credential stub                  | `orders-api.ts`, `pickup-credentials.tsx` | Honest placeholder when API returns `stub: true`            |
| Invoice link stub                       | `orders-api.ts`, `invoice-link.tsx`       | Placeholder when invoice not yet generated                  |
| T2 KYC upgrade stub                     | `onboarding/status-screen.tsx`            | i18n stub copy for tier-2 flow                              |
| PDF payout statement                    | `payouts-view.tsx`                        | CSV works; PDF shows stub message                           |
| Theme activation                        | `admin/theme/page.tsx`                    | Read-only; requires deploy env change                       |
| `generateStaticParams` placeholder UUID | `disputes/[id]`                           | Build-time only, not runtime mock                           |

**No MSW or mock API layer** in production code paths.

---

## API endpoints without frontend consumers

| Endpoint area               | Notes                                        |
| --------------------------- | -------------------------------------------- |
| `/admin/search-insights/*`  | No admin UI page                             |
| `/admin/governance/vendors` | No admin UI page                             |
| `/beta/invites` (admin)     | Beta page uses redeem, not invite management |
| `/internal/sentry-test`     | Dev/ops only                                 |
| COD endpoints               | Verify UI wiring for COD confirm/refuse      |

---

## Frontend calls without verified production endpoints

| Call                                    | Risk                                         |
| --------------------------------------- | -------------------------------------------- |
| `localhost:8000/cart` on production     | **P0** — env misconfiguration, not dead code |
| Admin dashboard if API admin routes 404 | **Ruled out** — prod returns 401             |

---

## Database tables with no application usage

| Table                    | Rows | Notes                             |
| ------------------------ | ---- | --------------------------------- |
| `reconciliation_reports` | 0    | Awaiting first reconciliation run |
| `ask_cache`              | 0    | No cache hits yet                 |
| `beta_invites`           | 0    | Beta system unused                |
| `translation_overrides`  | 0    | Admin translations unused         |
| `flags`                  | 0    | No user reports                   |
| `business_buyers`        | 0    | B2B not activated                 |

All have API/UI code paths — unused due to pre-launch state, not dead schema.

---

## Workflows referenced but inactive

| Workflow            | Code reference                  | Status                                                                       |
| ------------------- | ------------------------------- | ---------------------------------------------------------------------------- |
| DB backup           | `infra/n8n/`, restore-drill CI  | Inactive                                                                     |
| Error alert         | n8n settings.errorWorkflow      | Unpublished                                                                  |
| Abandoned cart tick | `/internal/n8n/abandoned-carts` | API exists; n8n schedule in operational nudges? — covered in nudges workflow |

---

## Test-only mocks (not production)

- Extensive `vi.mock()` in vitest/pytest
- `conftest.py` safe env defaults for pytest
- E2E may use test credentials (not in repo)

---

## Obsolete / stale references

| Item                              | Notes                                             |
| --------------------------------- | ------------------------------------------------- |
| Branch `claude/nice-knuth-ijvthu` | Deleted per AGENTS.md                             |
| Migration 0071 in prod, not repo  | Schema drift — not dead code but orphan migration |

---

## Recommendations

1. Add vendor nav items or hub page for orphaned routes (R-004)
2. Remove unused `OrphanedTierItem` type or implement UI
3. Build admin pages for search-insights and governance APIs
4. Sync migration 0071 to repo
