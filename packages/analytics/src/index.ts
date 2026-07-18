/**
 * @vergeo/analytics — consent-aware, data-frugal client analytics.
 *
 * The GA4 mirror is a convenience only; the server event log (funnel + search +
 * the unified `analytics_event_stream`) is the ad-blocker-proof source of truth.
 *
 * The React `AnalyticsProvider` is a client component and is exported from the
 * dedicated `@vergeo/analytics/provider` entry to keep this index server-safe.
 */

export {
  CONSENT_COOKIE,
  getAnalyticsConsent,
  hasAnalyticsConsent,
  setAnalyticsConsent,
  type ConsentState,
} from "./consent";
export { type AnalyticsEventMap, type AnalyticsEventName, type MoneyNgwee } from "./events";
export { getSessionId } from "./session";
export { flush, MAX_BATCH, track } from "./track";
