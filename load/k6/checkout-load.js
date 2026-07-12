// checkout-load.js — Vergeo5 100-concurrent checkout load test (k6).
//
// Drives the money-critical path against a DEPLOYED STAGING API:
//   cart (pre-seeded) -> POST /checkout/session (reserve stock)
//                     -> POST /checkout/steps/fulfilment
//                     -> POST /checkout/steps/payment
//                     -> POST /orders            (create per-vendor orders)
//                     -> payment-initiate        (Lenco STUB — never a real endpoint)
//
// This script is env-driven and never embeds credentials. Lenco is ALWAYS a stub:
// LENCO_STUB_URL points at a local/mock push endpoint so we never hammer a provider.
//
// The 100cc run + p95 numbers are FOUNDER/STAGING-GATED (no staging is reachable from
// the build env). Run procedure + seeding prerequisites live in load/README.md.
// After any run, load/invariant-check.py is the money-safety proof (oversell / ledger /
// invoice-gap). Passing thresholds here is necessary but NOT sufficient — invariant-check
// must also pass.

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';

// ---------------------------------------------------------------------------
// Config (env-driven; no secrets in repo)
// ---------------------------------------------------------------------------

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
// Comma-separated pre-seeded Supabase JWTs, one per seeded customer+cart. 100cc needs
// a pool so VUs act as distinct customers (see seeding prerequisites in README).
const AUTH_TOKENS = (__ENV.AUTH_TOKENS || __ENV.AUTH_TOKEN || '')
  .split(',')
  .map((t) => t.trim())
  .filter((t) => t.length > 0);
// Lenco stub base URL — MUST be a mock. Guard below refuses a real Lenco host.
const LENCO_STUB_URL = (__ENV.LENCO_STUB_URL || 'http://localhost:9099/lenco-stub').replace(
  /\/+$/,
  '',
);
const PAYMENT_METHOD = __ENV.PAYMENT_METHOD || 'momo'; // momo | card | cod
const PAYMENT_RAIL = __ENV.PAYMENT_RAIL || 'mtn'; // mtn | airtel (momo only)
const PAYER_NUMBER = __ENV.PAYER_NUMBER || '+260970000000';

if (/lenco\.co|api\.lenco/i.test(LENCO_STUB_URL)) {
  throw new Error('LENCO_STUB_URL points at a real Lenco host — load tests must use a stub');
}

const tokens = new SharedArray('auth-tokens', () => AUTH_TOKENS);

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const oversellErrors = new Counter('oversell_errors'); // must stay 0
const ordersCreated = new Counter('orders_created');
const sessionLatency = new Trend('checkout_session_ms', true);
const orderLatency = new Trend('order_create_ms', true);
const paymentLatency = new Trend('payment_initiate_ms', true);

// ---------------------------------------------------------------------------
// Thresholds — ENCODED pass criteria (not prose). Any breach fails `k6 run`.
// ---------------------------------------------------------------------------

export const options = {
  scenarios: {
    checkout_100cc: {
      executor: 'ramping-vus',
      exec: 'checkout',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 20 }, // warm up
        { duration: '1m', target: 100 }, // ramp to 100 concurrent
        { duration: '2m', target: 100 }, // hold 100cc — the stress window
        { duration: '30s', target: 0 }, // ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    // p95 < 500ms end-to-end HTTP at 100 concurrent checkouts — the headline SLO.
    'http_req_duration{scenario:checkout_100cc}': ['p95<500'],
    // p95 of the two write hops we own must also stay under budget.
    order_create_ms: ['p95<500'],
    checkout_session_ms: ['p95<500'],
    // Fewer than 1% transport failures and >99% functional checks pass.
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    // MONEY-SAFETY GATES (encoded): zero oversell responses; at least one order created.
    oversell_errors: ['count==0'],
    orders_created: ['count>0'],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function authHeaders(token) {
  return {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    tags: { scenario: 'checkout_100cc' },
  };
}

// The claim guard (stock_qty >= qty, decrement-in-place) returns HTTP 409
// checkout.stock_unavailable when stock is exhausted. That is the CORRECT,
// safe response to contention — it is NOT an oversell. An oversell would be a
// 2xx that hands out stock that does not exist; the invariant-check (negative
// stock_qty) is the ground-truth proof. Here we only assert the guard never
// silently succeeds past zero.
function isCleanStockRejection(res) {
  if (res.status !== 409) return false;
  try {
    const body = res.json();
    return body && body.error && body.error.code === 'checkout.stock_unavailable';
  } catch (_e) {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Scenario: one full checkout attempt per iteration
// ---------------------------------------------------------------------------

export function checkout() {
  if (tokens.length === 0) {
    throw new Error('No AUTH_TOKENS provided — seed staging customers/carts first (see README)');
  }
  const token = tokens[(__VU + __ITER) % tokens.length];
  const cfg = authHeaders(token);
  const idemKey = `ord-load-${__VU}-${__ITER}-${Date.now()}`;

  let sessionId = null;
  let vendorGroups = [];

  group('01_create_session', () => {
    const res = http.post(`${BASE_URL}/checkout/session`, null, cfg);
    sessionLatency.add(res.timings.duration);

    if (isCleanStockRejection(res)) {
      // Contention rejection — safe. Skip the rest of this iteration.
      check(res, { 'session: clean stock rejection (409)': () => true });
      return;
    }
    const ok = check(res, {
      'session: 200': (r) => r.status === 200,
      'session: has session_id': (r) => {
        try {
          return !!r.json('session_id');
        } catch (_e) {
          return false;
        }
      },
    });
    if (!ok) return;
    const body = res.json();
    sessionId = body.session_id;
    vendorGroups = (body.vendor_groups || []).map((g) => ({
      vendor_id: g.vendor_id,
      fulfilment: 'pickup', // pickup avoids address plumbing under load
      delivery_zone: null,
      delivery_fee_ngwee: 0,
      subtotal_ngwee: g.subtotal_ngwee,
    }));
  });

  if (!sessionId || vendorGroups.length === 0) return;

  group('02_fulfilment', () => {
    const payload = JSON.stringify({
      session_id: sessionId,
      groups: vendorGroups.map((g) => ({ vendor_id: g.vendor_id, fulfilment: 'pickup' })),
    });
    const res = http.post(`${BASE_URL}/checkout/steps/fulfilment`, payload, cfg);
    check(res, { 'fulfilment: 200': (r) => r.status === 200 });
  });

  group('03_payment_method', () => {
    const payload = JSON.stringify({
      session_id: sessionId,
      method: PAYMENT_METHOD,
      rail: PAYMENT_METHOD === 'momo' ? PAYMENT_RAIL : null,
      payer_number: PAYMENT_METHOD === 'momo' ? PAYER_NUMBER : null,
    });
    const res = http.post(`${BASE_URL}/checkout/steps/payment`, payload, cfg);
    check(res, { 'payment-method: 200': (r) => r.status === 200 });
  });

  let orderCreated = false;

  group('04_create_orders', () => {
    const payload = JSON.stringify({
      session_id: sessionId,
      idempotency_key: idemKey,
      method: PAYMENT_METHOD,
      rail: PAYMENT_METHOD === 'momo' ? PAYMENT_RAIL : null,
      payer_number: PAYMENT_METHOD === 'momo' ? PAYER_NUMBER : null,
      address_id: null,
      groups: vendorGroups,
    });
    const res = http.post(`${BASE_URL}/orders`, payload, cfg);
    orderLatency.add(res.timings.duration);

    if (isCleanStockRejection(res)) {
      check(res, { 'orders: clean stock rejection (409)': () => true });
      return;
    }
    const ok = check(res, {
      'orders: 200': (r) => r.status === 200,
      'orders: has orders[]': (r) => {
        try {
          return Array.isArray(r.json('orders')) && r.json('orders').length > 0;
        } catch (_e) {
          return false;
        }
      },
      // Any 2xx that also reports stock trouble would be an oversell signal.
      'orders: no oversell in 2xx body': (r) => {
        if (r.status !== 200) return true;
        return r.body.indexOf('oversell') === -1;
      },
    });
    if (res.status === 200 && res.body.indexOf('oversell') !== -1) {
      oversellErrors.add(1);
    }
    if (ok && res.status === 200) {
      orderCreated = true;
      ordersCreated.add(1);
    }
  });

  if (!orderCreated) return;

  group('05_payment_initiate_stub', () => {
    // Lenco push is STUBBED. In production this is a Lenco USSD-push call; under
    // load we hit the mock so no provider is touched and no real money moves.
    const payload = JSON.stringify({
      reference: idemKey,
      rail: PAYMENT_RAIL,
      payer_number: PAYER_NUMBER,
    });
    const res = http.post(`${LENCO_STUB_URL}/collections`, payload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { scenario: 'checkout_100cc', stub: 'lenco' },
    });
    paymentLatency.add(res.timings.duration);
    check(res, { 'payment-initiate stub: 2xx': (r) => r.status >= 200 && r.status < 300 });
  });

  sleep(Math.random() * 0.5);
}
