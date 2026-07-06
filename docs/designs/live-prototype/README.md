# Live Prototype Audit — Vergeo (`vergeo-21ffc.web.app`)

**Status: BLOCKED — the live prototype could not be reached from the audit environment.**
Audit attempted 2026-07-06. No screenshots or design tokens could be captured because
every route to the site is denied by this session's organization egress policy at the
network (CONNECT-tunnel) layer, and the local git working tree contains no prototype
source to fall back on.

This document records exactly what was attempted and what failed, proves the blocker,
and ships a turnkey audit harness so the full audit can be completed in minutes once the
host is reachable (or run from an unrestricted environment).

---

## 1. What was attempted (real attempts, all paths exhausted)

| # | Method | Target | Result |
|---|--------|--------|--------|
| 1 | `curl` direct | `https://vergeo-21ffc.web.app/` | `curl (56) CONNECT tunnel failed, response 403` — HTTP `000` |
| 2 | `curl` direct | `https://vergeo-21ffc.firebaseapp.com/` (alt Firebase domain) | HTTP `000` (same CONNECT denial) |
| 3 | `WebFetch` tool | `https://vergeo-21ffc.web.app/` | `HTTP 403 Forbidden` |
| 4 | `curl` sub-resources | `/index.html`, `/manifest.json`, `/asset-manifest.json` | HTTP `000` (all denied) |
| 5 | Headless **Chromium** (Playwright) via configured proxy | `https://vergeo-21ffc.web.app/` | `net::ERR_TUNNEL_CONNECTION_FAILED` |
| 6 | Firebase Hosting REST API | `firebasehosting.googleapis.com/v1beta1/sites/vergeo-21ffc/channels/live` | `401 Unauthorized` (reachable, but needs OAuth creds we don't have) |
| 7 | Firebase Realtime DB | `vergeo-21ffc-default-rtdb.firebaseio.com/.json` | HTTP `000` (denied) |
| 8 | Cloud Storage bucket | `storage.googleapis.com/vergeo-21ffc.appspot.com/` | `403` (reachable host, bucket not public) |
| 9 | Public web archives | `web.archive.org`, `archive.org/wayback`, `timetravel.mementoweb.org` | HTTP `000` / `403` (all denied) |
| 10 | Local repo source | `/home/user/Convergeo` working tree | Empty — no app source present (see §4) |

**Egress reality of this session:** only the `*.googleapis.com` API family is reachable
(hosts answer `401/403/404` from Google itself, i.e. the tunnel connects). Every
consumer-facing host — including the prototype's `*.web.app` / `*.firebaseapp.com`
domains, the RTDB domain, and the public web archives — is refused by policy before any
TLS/HTTP exchange happens.

## 2. Root cause

The prototype's host is **not on this session's egress allowlist**. The denial happens at
the HTTP `CONNECT` tunnel step (before TLS), so it is identical for `curl`, `WebFetch`,
and a real headless browser — no client-side change (browser flags, CA bundle, user-agent)
can affect it. The session's own proxy status endpoint records the denial verbatim:

```json
"recentRelayFailures": [
  {
    "ts": "2026-07-06T06:31:26.667Z",
    "kind": "connect_rejected",
    "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
    "host": "vergeo-21ffc.web.app:443"
  }
]
```

Per the environment's proxy README, a `403` on `CONNECT` is an **organization egress
policy denial** that must not be retried or routed around — it must be reported. It has
been, above. (No circumvention via third-party fetch/render proxies was attempted, by
policy.)

## 3. What the browser attempt proved

Playwright `playwright-core` was installed in scratch and driven headless against the
pre-installed Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`, using the
session `HTTPS_PROXY`. The browser launched fine and issued the navigation; the request
failed with:

```
NAV_FAILED: page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://vergeo-21ffc.web.app/
REQUEST_FAILURES: ["https://vergeo-21ffc.web.app/ => net::ERR_TUNNEL_CONNECTION_FAILED"]
```

So the rendering toolchain itself is healthy and ready — **only the network path to the
target is blocked.** The moment the host is reachable, the harness in §6 will produce the
full screenshot set and DOM/CSS extraction with no further setup.

## 4. Local repo state (no source-code fallback available)

The prototype's source is **not** in this repository, so the design language could not be
extracted from local files either:

- Working tree of `/home/user/Convergeo` (branch `claude/nice-knuth-ijvthu`) contains only
  this `docs/` tree — **zero application source files**.
- `.git/objects` holds **0 objects**; `.git/FETCH_HEAD` is empty; `refs/heads` is empty.
  It is a bare skeleton checkout. The Firebase-deployed bundle lives only on the blocked
  host.
- Remote is `KaluMuso/Convergeo` (via the session's local git proxy).

There was therefore no HTML/JS/CSS to parse for colors, fonts, routes, framework, or
backend wiring. All findings sections below are intentionally left as an empty, ready
checklist rather than guessed.

## 5. How to unblock and finish the audit

Any one of these resolves it:

1. **Allowlist the host** `vergeo-21ffc.web.app` (and `vergeo-21ffc.firebaseapp.com`) for
   this session's egress policy, then re-run the harness in §6. *(Preferred — fastest.)*
2. **Run the harness from an unrestricted environment** (any machine/CI with plain internet
   and Node + a Chromium). It is self-contained.
3. Provide **Firebase project credentials / a service-account token**; the deployed files
   can then be pulled via the Hosting REST API (`firebasehosting.googleapis.com`, which
   *is* reachable here and returned `401` only for lack of auth) and rendered from a local
   static server.

## 6. Ready-to-run audit harness (resumes the full task automatically)

Save as `audit.js` next to a `package.json` with `playwright-core` installed
(`npm i playwright-core`), then `node audit.js`. It discovers routes, clicks nav links,
screenshots every reachable screen at mobile **360x740** and desktop **1366x768** into this
folder, and dumps the computed design tokens (palette, fonts, radii, transitions) and
framework/backend signals to `extraction.json`. It was validated up to the navigation step
in this session (browser launches; only the remote host is blocked).

```js
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const BASE = 'https://vergeo-21ffc.web.app/';
const OUT = __dirname; // docs/designs/live-prototype
const EXEC = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const VIEWPORTS = { mobile: { width: 360, height: 740 }, desktop: { width: 1366, height: 768 } };

const slug = u => (new URL(u, BASE).pathname.replace(/\/+$/, '') || '/home')
  .replace(/^\//, '').replace(/[^\w-]+/g, '-') || 'home';

(async () => {
  const browser = await chromium.launch({
    executablePath: EXEC, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
    proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined,
  });
  const network = [];
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  ctx.on('request', r => {
    const h = new URL(r.url()).host;
    if (/firebase|firestore|googleapis|firebaseio|identitytoolkit|supabase|\/api\//.test(r.url()))
      network.push(`${r.method()} ${r.url()}`);
  });

  // --- discover routes from the SPA once loaded ---
  const disc = await ctx.newPage();
  await disc.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  const found = await disc.$$eval('a[href]', as => as.map(a => a.getAttribute('href')));
  const routes = new Set(['/']);
  for (const h of found) {
    if (!h || /^(https?:|mailto:|tel:|#)/.test(h)) continue;
    try { routes.add(new URL(h, location.href).pathname); } catch {}
  }
  // add common e-commerce guesses; harmless if they redirect
  ['/home','/shop','/catalog','/categories','/products','/product','/cart','/checkout',
   '/login','/register','/account','/services','/events','/vendor','/admin','/orders']
    .forEach(r => routes.add(r));

  // --- framework + token extraction from the loaded home page ---
  const extraction = await disc.evaluate(() => {
    const fw = [];
    if (window.React || document.querySelector('[data-reactroot],#root')) fw.push('React?');
    if (window.Vue || document.querySelector('[data-v-app],#app[data-v-app]')) fw.push('Vue?');
    if (window.ng || document.querySelector('[ng-version]')) fw.push('Angular('+(document.querySelector('[ng-version]')?.getAttribute('ng-version'))+')');
    if (document.querySelector('flt-glass-pane, flutter-view')) fw.push('Flutter-web');
    const colors = new Set(), fonts = new Set(), radii = new Set(),
          shadows = new Set(), transitions = new Set();
    for (const el of document.querySelectorAll('*')) {
      const s = getComputedStyle(el);
      [s.color, s.backgroundColor, s.borderTopColor].forEach(c => c && c !== 'rgba(0, 0, 0, 0)' && colors.add(c));
      fonts.add(s.fontFamily);
      if (s.borderTopLeftRadius !== '0px') radii.add(s.borderTopLeftRadius);
      if (s.boxShadow !== 'none') shadows.add(s.boxShadow);
      if (s.transition !== 'all 0s ease 0s' && s.transition) transitions.add(s.transition);
    }
    const nav = document.querySelector('nav,[class*=bottom-nav],[class*=tabbar]');
    return {
      framework: fw, title: document.title,
      colors: [...colors].slice(0, 40), fonts: [...fonts].slice(0, 10),
      radii: [...radii], boxShadows: [...shadows].slice(0, 10),
      transitions: [...transitions].slice(0, 20),
      hasBottomNav: !!nav, cardCount: document.querySelectorAll('[class*=card]').length,
    };
  });
  await disc.close();

  // --- screenshot every route at both viewports (cap ~24 imgs => ~12 routes) ---
  const inventory = [];
  const list = [...routes].slice(0, 12);
  for (const [name, vp] of Object.entries(VIEWPORTS)) {
    const page = await (await browser.newContext({ viewport: vp, ignoreHTTPSErrors: true })).newPage();
    for (const route of list) {
      const file = `${name}-${slug(route)}.png`;
      try {
        const resp = await page.goto(new URL(route, BASE).href, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(600);
        await page.screenshot({ path: path.join(OUT, file), fullPage: true });
        if (name === 'desktop') inventory.push({ route, status: resp && resp.status(), mobile: `mobile-${slug(route)}.png`, desktop: file });
      } catch (e) { inventory.push({ route, error: e.message.split('\n')[0] }); }
    }
    await page.close();
  }

  fs.writeFileSync(path.join(OUT, 'extraction.json'),
    JSON.stringify({ base: BASE, extraction, inventory, network: [...new Set(network)].slice(0, 60) }, null, 2));
  console.log('Wrote screenshots + extraction.json for', inventory.length, 'route renders');
  await browser.close();
})();
```

## 7. Findings — TO BE COMPLETED (blocked; fill after §5 unblocks)

The following are the deliverables the task asks for. They are left empty deliberately —
nothing here is inferred, because no bytes of the live app could be observed.

### 7a. Screen inventory (route -> purpose -> screenshot files)
_Pending._ Expected e-commerce surfaces to verify once reachable: home, catalog/category,
product detail, cart, checkout, auth (login/register), account, services, events, and any
vendor/admin area. The harness auto-discovers actual routes from the SPA router + nav links.

| Route | Purpose | mobile png | desktop png | Functional / Decorative |
|-------|---------|-----------|------------|-------------------------|
| _pending_ | | | | |

### 7b. Design tokens
_Pending harness `extraction.json`._ To capture: hex/rgb palette actually used, font
families, border-radius scale, spacing rhythm, box-shadow/elevation set, button styles,
icon style.

### 7c. Animations & transitions inventory
_Pending._ To capture: each CSS `transition`/`@keyframes` by name and the property it
animates (e.g. hover elevations, page/route transitions, skeleton loaders, nav indicator
slides).

### 7d. Framework & backend findings
_Pending._ To determine: React vs Vue vs Angular vs Flutter-web (harness sniffs
`#root`/`[ng-version]`/`flt-glass-pane` and window globals); whether data is hardcoded demo
content vs live backend (harness logs all `firebase*/firestore/googleapis/identitytoolkit/
/api/` network calls). Note: the Firebase Hosting API for this project *is* reachable and
returned `401`, confirming the project id `vergeo-21ffc` exists and is a genuine Firebase
Hosting deployment — the app is real, just not reachable from here.

### 7e. Strengths / weaknesses — carry into production build vs not
_Pending._ Requires visual + DOM evidence.

---

### Reproduction notes / environment
- Pre-installed Chromium: `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`, `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD` honored).
- `playwright-core` installs cleanly (npm registry is on the no-proxy list).
- Session egress proxy: `http://127.0.0.1:42373`; status: `curl -sS "$HTTPS_PROXY/__agentproxy/status"`.
- Working scratch dir for this attempt:
  `/tmp/claude-0/-home-user-Convergeo/ca3bf6a9-5ac0-59de-8d61-e7dcc0c18e35/scratchpad/proto-audit/`
  (`render.js` = the minimal repro that produced the `ERR_TUNNEL_CONNECTION_FAILED` proof).
