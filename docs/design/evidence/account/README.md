# Phase 4.4 — Account, saved items & recently viewed

**Base SHA:** `d9839db349887ab48a52c18546e05961a62498d6` (`master`)  
**Working branch:** `cursor/customer-account-engagement-077d`  
**Audit refs:** `docs/design/vergeo5-ui-ux-audit.md` §4.9, §5.1, §5.4, E19, E23, E24

## Live vs repository drift

| Area                   | Live / audit                        | Repo at base                                              |
| ---------------------- | ----------------------------------- | --------------------------------------------------------- |
| Theme in navbar        | Relocate to Preferences             | Already relocated; footer “Display preferences”           |
| Account hub            | Proposed Orders·Tickets·Jobs·Saved… | Nav = Profile·Addresses·Preferences·Business·Privacy only |
| `/account`             | Hub                                 | Profile form only                                         |
| Wishlist page          | Missing                             | Local heart toggle only (`vergeo5:wishlist:v1`)           |
| Recently viewed        | Missing                             | Analytics `product_view` only — no local history UI       |
| Sign out               | In account menu                     | Only via privacy delete flow                              |
| Shop chrome on account | Weak                                | Account outside `(shop)` layout                           |

## Proposed account sitemap (implemented)

```
/[locale]/account              → Overview hub
/[locale]/account/orders…
/[locale]/account/tickets…
/[locale]/account/jobs…
/[locale]/account/profile
/[locale]/account/addresses
/[locale]/account/preferences  → theme system/light/dark + notifications
/[locale]/account/business
/[locale]/account/privacy
/[locale]/account/recent       → local recently viewed (clearable)
/[locale]/wishlist             → Saved items (shop chrome; works signed-out)
```

**Nav order:** Overview · Orders · Tickets · Jobs · Saved · Addresses · Preferences · Profile · Business · Privacy · Sign out

Unsupported capabilities are not shown as operational (no fake sync, no stock reservation claim).

## Preference architecture

| Pref          | Storage                                             | Default      | UI                           |
| ------------- | --------------------------------------------------- | ------------ | ---------------------------- |
| Theme         | `localStorage` `vg-theme` + `ThemeScript` pre-paint | `system`     | Account → Preferences radios |
| Language      | Profile API + locale route                          | route locale | Profile language select      |
| Location      | Addresses API                                       | —            | Addresses                    |
| Currency      | ZMW only (locked)                                   | ZMW          | Not selectable               |
| Notifications | Account preferences API                             | server       | Preferences switches         |

## Recently viewed behaviour

| Rule             | Value                                                  |
| ---------------- | ------------------------------------------------------ |
| Storage          | Device `localStorage` key `vergeo5:recently-viewed:v1` |
| Max items        | 20                                                     |
| Dedup            | Move existing slug to front on re-view                 |
| Retention        | Until cleared or overwritten (no TTL backend)          |
| Signed-out       | Same device store                                      |
| Cross-device     | Not synced (honest copy)                               |
| Clear            | Explicit “Clear history” on Recent page                |
| Deleted products | Shown as unavailable; removable                        |

## Safety

- Account routes remain `robots: noindex`, auth-gated.
- No new payment/ledger changes.
- Wishlist does not claim stock/price reservation.

## Verification

- Lint / typecheck / customer tests (376) / production build — pass
- Phase-1 i18n overlays — pass
- Signed-out `/account` → `/login?next=/en/account`
- `/wishlist` renders empty + disclaimer without auth
- Theme remains in Preferences (system/light/dark); not in primary nav

## Known limitations

- Account still outside shop bottom-nav chrome (link “Back to shopping” added).
- Wishlist / recently viewed are device-local only (no cross-device sync).
- Move-to-cart depends on API + cart session.
- Signed-in overview screenshots require real credentials.

## Recommended next PR

Server-side wishlist sync after sign-in; optional shop-chrome shell for account; wire recent rail on home.
