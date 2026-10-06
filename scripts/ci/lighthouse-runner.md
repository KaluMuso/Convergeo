# Performance runner

`pnpm perf:lighthouse` replaces LHCI autorun with the official Lighthouse Node API,
chrome-launcher and Puppeteer's pinned Chrome for Testing. Install dependencies,
then run `pnpm exec puppeteer browsers install chrome`. `pnpm perf:lighthouse:test`
runs offline contract tests. Node remains 22 (the selected packages require at least
22.19); CI uses the repository's existing Node setup.

The hosted performance job uses GitHub's Ubuntu 24.04 image and its installed
Google Chrome at `/opt/google/chrome/chrome`, selected only for the Lighthouse
step through `PUPPETEER_EXECUTABLE_PATH`. Before collection, the job requires
that executable to belong to `google-chrome-stable`, report exactly
`154.0.8037.97`, and have installed package version `154.0.8037.97-1` on
image `ubuntu24/20261004.327.1`. This check runs immediately after checkout
and again after Chrome for Testing acquisition, recording only fixed identity
labels. The older `20260927.320.1` image with Chrome `154.0.8037.57` and all
unknown combinations fail before database setup or app build. A mismatch fails
without installing a package or selecting another browser.
This pin follows [Google's Linux Stable release](https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop.html),
[GitHub's Ubuntu 24.04 image update](https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20261004.327),
and [Google's Debian package index](https://dl.google.com/linux/chrome/deb/dists/stable/main/binary-amd64/Packages.gz).
The official Puppeteer-pinned Chrome for Testing download remains required;
local runs continue to select it by default. The hosted selection uses the
installed Chrome's normal sandbox and stock host policy without moving binaries
or changing policy. Puppeteer's Chrome for Testing revision is `154.0.8037.57`;
hosted Lighthouse uses the distinct installed `154.0.8037.97` package.
Browser launch and all five routes must pass the unchanged budgets. The workflow
collects Lighthouse only for the candidate and applies absolute assertions;
its base-build comparison covers bundles only. Earlier `154.0.8037.57` scores
are not a relative baseline for this browser. Any future Lighthouse comparison
must measure base and candidate with the same `154.0.8037.97` runtime and settings.

`lighthouserc.json` remains the policy source. This migration does not change its
five URLs, three runs per URL, mobile screen/network/CPU settings, thresholds,
checkout SEO warning or bundle budgets. Performance/LCP aggregate each metric's
median. Other assertions retain LHCI's default optimistic aggregation, including
its finite-value handling. Unsupported policy options fail rather than silently
being ignored. Missing runs, unrecovered runtime errors and unmatched final URLs fail.

Each run launches a fresh headless Chrome with its normal sandbox and certificate
validation. Collection exceptions stop further collection and preserve partial
evidence. No application server is started, URLs rewritten or external report
upload performed by the runner. The existing workflow still builds, starts and
warms the same application URLs and retains its other blocking gates.
An unusable `NO_NAVSTART` trace with no performance metrics, timeout warning or
completed content check gets one fresh Chrome retry for the same URL and run.
The rejected JSON/HTML pair is retained separately and recorded in
`run-summary.json`; it never counts toward the required three valid runs.
Exhaustion and all other collection errors remain blocking.
Each Chrome startup summary now includes fixed trace-event counts, relative
navigation timings and main-frame association for that attempt when Lighthouse
returns a trace. It records neither raw trace events nor frame IDs, document
URLs, request contents or browser headers. An unavailable trace is marked as
such; it is not inferred from the report.

Artifacts remain under `.lighthouseci`, uploaded as `lighthouse-reports` even on
failure. Every successful collection writes a distinct `lhr-*.json` and HTML pair.
`manifest.json` retains URL, report paths, category summary and representative-run
fields (closest to median FCP/TTI, separately from per-metric assertion medians).
`assertion-results.json` contains failing assertions including warnings, as before.
`assertion-results-all.json` additionally records successes; `run-summary.json`
records collection failures, engine versions, settings and the exit status.
The summary also retains each report's `runWarnings` with its URL and run number.
The pinned engine's page-load timeout warning means results may be incomplete:
it fails collection and assertion qualification even when all score floors pass.
The JSON and HTML for that failed measurement are retained; collection stops
without retrying or changing load timeouts. Informational warnings retain their
existing nonblocking behavior, and checkout's SEO assertion remains warning-only.
Only reports collected by the current invocation are evaluated; older files never
supply missing results. Exit 1 means a collection/configuration failure or an
error-level assertion failure. Other report notices and warning-only assertions
alone keep exit 0.

Performance CI additionally enables an isolated fixture harness. It selects the
actual assigned RFC1918 IPv4 on the default interface, sets the explicit preview
plane before both builds, and binds FastAPI only to that address. The upstream
resolver, CSP, TLS checks and browser sandbox remain unchanged. A finite
same-origin proxy transports GET cart, exact product and Electronics catalog
requests. It also admits three existing POST endpoints: genuinely empty cart
revalidation, fixture-only listing views with a valid session UUID, and bounded
customer error beacons. POST requires the exact frontend Origin and bounded,
validated payloads; only cart endpoints forward caller cart credentials.
Redirects, arbitrary paths/queries and ambient authentication headers are refused.
Ordinary builds leave both proxy and media endpoints unavailable. The home hero's
1440px source request maps only in this harness to the owned 1200px variant;
the five asset bytes, normal responsive srcset and ordinary image behavior stay fixed.

The disposable local Supabase database receives exactly two image operations:
the existing `phone_a` image becomes `ci-perf/smartphone-x1`, and the exact cheaper
`demo_gadget` gains a demo marker so the existing exclusion policy hides it.
The script checks the canonical local DSN and all expected preimages atomically;
listing/product/vendor identities, prices, stock and selection behavior stay
unchanged. Repository-owned WebP illustration variants are served only by the
gated fixture endpoint, never uploaded or installed in shared data.

After each complete measurement, the runner inspects the actual remaining browser
page without navigating or changing metrics. Home/category/PDP qualification requires
the exact API identities, one intended seller, visible product/seller/price and
naturally loaded local fixture media. Fallbacks, substituted listings or broken
images fail and retain genuine reports plus `content-readiness.json`. Home must
also render its hero; search and checkout must render their actual forms. Visible
error boundaries or skeletons fail every target. Bounded public field/visibility
diagnostics identify failed predicates without recording HTML, API bodies, headers
or storage. An incomplete
load warning still fails first; it never qualifies content or assertion scores.

Lighthouse 13 is a measurement-engine change. Offline assertion equivalence is
necessary but does not establish browser compatibility or preserve measured
scores. Before adopting this local proposal, independently qualify official
browser download/extraction/launch, a harmless local fixture, and all five built
application routes with the unchanged gates. A failed browser acquisition or
application build is NOT_RUN for dependent browser checks, never a score waiver.
Do not disable Chrome's sandbox, substitute mock LHRs, reroute failed downloads,
or lower assertions to obtain a pass.

Official interfaces:

- https://github.com/GoogleChrome/lighthouse/blob/main/docs/readme.md#using-programmatically
- https://pptr.dev/guides/configuration
- https://pptr.dev/browsers-api

The old `@lhci/cli` / `@lhci/utils` dependencies are removed rather than overridden.
The explicit `yauzl` 3.4 peer satisfies `@puppeteer/browsers`' supported range; its
native extraction path uses platform tools first. Only official browser artifacts
are in scope for installation, not arbitrary archives.
