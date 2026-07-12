# Analytics event dictionary (M16-P05)

Vergeo5 analytics has **one queryable schema** with two writers:

- **Server log — source of truth (ad-blocker-proof).** Written server-side by the
  API. Three streams, unified by migration `0029`:
  - `funnel_events` (0025) — checkout funnel stages.
  - `search_query_log` (0027) — search / Ask queries (anonymized, 30-day PII trim).
  - `analytics_events` (0029) — superset sink for events that have no dedicated
    table (e.g. the client-mirrored `product_view` / PDP step).
    All three are read through the **`analytics_event_stream`** view in one canonical
    shape (`source, event_type, session_id, user_id, entity_type, entity_id, props,
created_at`).
- **GA4 mirror — convenience only.** The `@vergeo/analytics` client wrapper mirrors
  a subset of events to GA4. It fires **only on consent**; the server log is always
  written and anonymized regardless of consent.

## Privacy & money rules

- **Anonymized regardless of consent.** No raw PII in the server log. `record_event`
  rejects raw-PII prop keys (`phone`, `email`, `address`, `landmark`, …). Search
  rows expose `normalized_term` only — never the raw `term`.
- **Consent gates GA4 only.** Refusal (or no decision yet) disables GA4; anonymized
  server beacons keep flowing. Consent lives in the `vg_analytics_consent` cookie.
- **Money is integer ngwee.** Every `*_ngwee` prop is an integer; `record_event`
  rejects floats/bools for money props. Never a major-unit decimal.
- **GA4 id** comes from `NEXT_PUBLIC_GA4_MEASUREMENT_ID` only (never hardcoded);
  absent id ⇒ no GA4.
- **RLS.** `analytics_events` is RLS + FORCE: service-role write, admin read, no
  client/anon read. The view is `security_invoker` so base-table RLS still applies.

## Canonical funnel

`search → product_view → cart → checkout → pay`

| Funnel step  | `event_type`(s)                                    | Stream source      |
| ------------ | -------------------------------------------------- | ------------------ |
| search       | `search`                                           | `search_query_log` |
| product_view | `product_view`                                     | `analytics_events` |
| cart         | `cart_add`                                         | `funnel_events`    |
| checkout     | `checkout_start`, `step_complete`, `payment_start` | `funnel_events`    |
| pay          | `order_placed`                                     | `funnel_events`    |

`app.services.analytics.events.query_funnel(days)` returns per-step counts over the
window from `analytics_event_stream`.

## Event payloads (client mirror + `analytics_events` props)

All money = integer ngwee. See `packages/analytics/src/events.ts` for the typed map.

| Event            | Props                                             |
| ---------------- | ------------------------------------------------- |
| `search`         | `normalized_term`, `zero_result`, `result_count?` |
| `product_view`   | `product_id`, `listing_id?`                       |
| `cart_add`       | `listing_id`, `qty`, `unit_price_ngwee`           |
| `checkout_start` | `checkout_group_id`, `total_ngwee`                |
| `payment_start`  | `checkout_group_id`, `method`, `total_ngwee`      |
| `order_placed`   | `checkout_group_id`, `order_count`, `total_ngwee` |

## Notes for operators

- The GA4 script (`googletagmanager.com/gtag/js`) is allowlisted in the customer
  app CSP by M15-P03; the wrapper loads it deferred/async, only after consent.
- The client beacon batches events and posts them with `navigator.sendBeacon` to
  `NEXT_PUBLIC_ANALYTICS_ENDPOINT` (default `/api/analytics/collect`) on tab hide —
  no per-event XHR, to stay cheap on 3G.
