# Performance runner

`pnpm perf:lighthouse` replaces LHCI autorun with the official Lighthouse Node API,
chrome-launcher and Puppeteer's pinned Chrome for Testing. Install dependencies,
then run `pnpm exec puppeteer browsers install chrome`. `pnpm perf:lighthouse:test`
runs offline contract tests. Node remains 22 (the selected packages require at least
22.19); CI uses the repository's existing Node setup.

`lighthouserc.json` remains the policy source. This migration does not change its
five URLs, three runs per URL, mobile screen/network/CPU settings, thresholds,
checkout SEO warning or bundle budgets. Performance/LCP aggregate each metric's
median. Other assertions retain LHCI's default optimistic aggregation, including
its finite-value handling. Unsupported policy options fail rather than silently
being ignored. Missing runs, runtime errors and unmatched final URLs fail.

Each run launches a fresh headless Chrome with its normal sandbox and certificate
validation. Collection exceptions stop further collection and preserve partial
evidence. No application server is started, URLs rewritten or external report
upload performed by the runner. The existing workflow still builds, starts and
warms the same application URLs and retains its other blocking gates.

Artifacts remain under `.lighthouseci`, uploaded as `lighthouse-reports` even on
failure. Every successful collection writes a distinct `lhr-*.json` and HTML pair.
`manifest.json` retains URL, report paths, category summary and representative-run
fields (closest to median FCP/TTI, separately from per-metric assertion medians).
`assertion-results.json` contains failing assertions including warnings, as before.
`assertion-results-all.json` additionally records successes; `run-summary.json`
records collection failures, engine versions, settings and the exit status. Only
reports collected by the current invocation are evaluated; older files never
supply missing results. Exit 1 means a collection/configuration failure or an
error-level assertion failure. Warnings alone keep exit 0.

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
