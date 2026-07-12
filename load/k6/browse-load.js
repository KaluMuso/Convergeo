// browse-load.js — Vergeo5 read-heavy browse/discovery load test (k6).
//
// Models the anonymous discovery mix a customer hits before checkout:
//   ~60% GET /search           (FTS + pg_trgm + pgvector RRF fusion)
//   ~30% GET /catalog/listings (PLP — category/filter/sort read path)
//   ~10% GET /search/suggest   (typeahead)
//
// Pure reads — no auth, no writes, no Lenco. Env-driven BASE_URL only.
// Latency thresholds are ENCODED; reads carry a tighter budget than checkout writes.
// The live 100cc/soak run is FOUNDER/STAGING-GATED (no staging reachable from build env).

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
const VUS = Number(__ENV.BROWSE_VUS || 100);

const searchLatency = new Trend('search_ms', true);
const plpLatency = new Trend('plp_ms', true);
const suggestLatency = new Trend('suggest_ms', true);

// Realistic Zambian-catalog query terms (kept in-repo, no PII).
const TERMS = new SharedArray('terms', () => [
  'cement',
  'solar panel',
  'maize meal',
  'phone',
  'fridge',
  'roofing sheet',
  'cooking oil',
  'water tank',
  'generator',
  'school shoes',
]);

const CATEGORY_PATHS = new SharedArray('categories', () => [
  'electronics',
  'building-materials',
  'groceries',
  'home-appliances',
  'fashion',
]);

const SORTS = ['relevance', 'price_asc', 'price_desc', 'newest'];

export const options = {
  scenarios: {
    browse_mix: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: Math.ceil(VUS / 5) },
        { duration: '1m', target: VUS },
        { duration: '2m', target: VUS },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '20s',
    },
  },
  thresholds: {
    // Reads must be fast on 3G-adjacent budgets — tighter than checkout writes.
    'http_req_duration{route:search}': ['p95<400'],
    'http_req_duration{route:plp}': ['p95<400'],
    'http_req_duration{route:suggest}': ['p95<250'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function doSearch() {
  const q = encodeURIComponent(pick(TERMS));
  const page = 1 + Math.floor(Math.random() * 3);
  const res = http.get(`${BASE_URL}/search?q=${q}&page=${page}&page_size=24`, {
    tags: { route: 'search' },
  });
  searchLatency.add(res.timings.duration);
  check(res, { 'search: 200': (r) => r.status === 200 });
}

function doPlp() {
  const cat = encodeURIComponent(pick(CATEGORY_PATHS));
  const sort = pick(SORTS);
  const res = http.get(`${BASE_URL}/catalog/listings?category_path=${cat}&sort=${sort}&limit=24`, {
    tags: { route: 'plp' },
  });
  plpLatency.add(res.timings.duration);
  check(res, { 'plp: 200': (r) => r.status === 200 });
}

function doSuggest() {
  const q = encodeURIComponent(pick(TERMS).slice(0, 4));
  const res = http.get(`${BASE_URL}/search/suggest?q=${q}&limit=8`, {
    tags: { route: 'suggest' },
  });
  suggestLatency.add(res.timings.duration);
  check(res, { 'suggest: 200': (r) => r.status === 200 });
}

export default function () {
  const roll = Math.random();
  if (roll < 0.6) {
    doSearch();
  } else if (roll < 0.9) {
    doPlp();
  } else {
    doSuggest();
  }
  sleep(Math.random() * 0.7);
}
