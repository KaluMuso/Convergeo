# Direct Lighthouse tooling and retired LHCI patch

The measurement command is now `pnpm perf:lighthouse --config=lighthouserc.json`.
Root development dependencies are pinned to Lighthouse **13.5.0** and
chrome-launcher **1.2.2**. Use Node **22.19 or later** (qualification uses
22.23.3) and pnpm **9.15.4**. The committed lockfile records the exact transitive
versions; resolve only this tooling closure when updating it.

The adapter requires an explicit `CHROME_PATH` to an existing executable. CI uses
`/usr/bin/google-chrome` and fails if it is unavailable. There is no browser
installer, automatic download, archive extraction, sandbox/TLS bypass, or
collection retry. The launcher constructor and effective flags are checked;
missing browsers, malformed or redirected reports, incomplete-load warnings,
collection failures and cleanup failures remain blocking. Reports and the failing
sample are retained under `.lighthouseci` even when assertions fail.

The existing `lighthouserc.json` URLs, three-run sampling, mobile/throttling
settings, score/LCP budgets and checkout SEO warning are unchanged. Every sample
must contain finite performance scores and LCP values before collection acceptance
and median evaluation; invalid values cannot reduce the three-sample population.
Zero is a valid measurement. Other categories preserve LHCI's supported
aggregation/null-value behavior. Unsupported policy fails rather than silently
disabling coverage. Root full Puppeteer and `yauzl`
are not added: neither is needed to measure an explicitly selected Chrome. The
browser library's optional archive peer can remain in the transitive lock; this
workflow does not invoke it and does not certify archive extraction safety.

The resolved graph removes LHCI, get-uri/basic-ftp, proxy-agent and extract-zip.
Consequently the old parser patch and its consumer-specific test are retired;
the historical provenance and notices below remain. Dependency auditing now runs
separate blocking production and full high-severity audits without advisory
waivers or exit-status suppression. API pip-audit remains mandatory. An audit
infrastructure error is a failure, never a clean report.

Focused checks (no browser or services required):

```sh
node --test scripts/ci/lighthouse-budget.test.mjs scripts/ci/lighthouse-dependencies.test.mjs scripts/ci/dependency-audit-contract.test.mjs scripts/ci/perf-reporting.test.mjs
node scripts/ci/validate-lighthouserc.mjs
pnpm install --frozen-lockfile --strict-peer-dependencies --ignore-scripts
pnpm audit --prod --audit-level high
pnpm audit --audit-level high
```

Offline tests cannot qualify real collection. Fresh builds, all five URLs and
three runs per URL, accessibility checks, and API pip-audit must bind to the final
source before acceptance. Earlier LHCI/donor results do not certify this change.

## Historical backport provenance — retired, not an active dependency

The remainder records the former patch at source `92421f5d`; its commands and
paths describe that historical implementation. They are not current checks.

# LHCI dependency patches

## basic-ftp 5.3.1 listing-parser backport

This local patch addresses GHSA-c475-qrg2-pj4r without upgrading get-uri's accepted
basic-ftp major or changing its transport API. It keeps package version **5.3.1**.
It does **not** clear version-based audit findings or authorize an exception.
The extract-zip advisories and all existing CI/QA policies remain unchanged.

The source is Patrick Juchli's official fix
[`d0d9e07c56e519587bb50532ac6eadbb0cb0cfe9`](https://github.com/patrickjuchli/basic-ftp/commit/d0d9e07c56e519587bb50532ac6eadbb0cb0cfe9),
released in 6.2.1. The two installed patched modules match the published 6.2.1
modules byte-for-byte; published 6.2.3 contains the same modules. No other 6.x
implementation is copied. The patch changes only `dist/parseListUnix.js` and
`dist/parseListDOS.js`; connection, TLS, transfers, public types and package
metadata retain their original 5.3.1 bytes.

The fix anchors both parsers and limits each Unix owner/group capture to eight
words. Inode/block-count prefixes and ordinary listing formats remain supported.
Junk prefixes and names exceeding the parser's capture budget are deliberately
rejected. Whitespace-separated owner/group fields are intrinsically ambiguous;
the limit bounds each capture, not a separately encoded server field.

### Provenance

Original and fixed packages were checked against the official npm SHA512
integrities. Original tarball SHA256:
`e7509e4985982ee4b44153d88199ba9646f9a9d434f0c2940d86de2f05a1a17c`.
Fixed 6.2.1 tarball SHA256:
`ce98b3508df1292431a7f591747385ceef971b55030aea32c976a3715dbe455e`.
These are integrity comparisons, not a claim to have verified npm publisher
signatures or to have obtained an upstream-supported 5.x release.

| Module                  | Original 5.3.1 SHA256                                              | Patched/published 6.2.1 SHA256                                     |
| ----------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| `dist/parseListUnix.js` | `458e9908eda5a17f523acd744052210a60c1fd3aa95f2a10ab2f731931081d2a` | `6596240aaaf766b5c9aa6b14f05cbefb734d8bc4b7dc5e3ac4688f9cabf32e33` |
| `dist/parseListDOS.js`  | `43dac80789172c57467428c4171b638b1a8fefbc060841ed282adf8bcfd26a1a` | `a902206c12ab1f8bf7360e5c143d02772e11747a4545a18d177507c5ac5a2cdf` |

Patch file: `patches/basic-ftp@5.3.1.patch`, SHA256
`30327decaf16e6465d90ed8b22e9a0bfc4985b292fb74597abf0cf67ae93aaaa`.
pnpm9.15.4 records patch hash `ytle2xgakdnjukyfqdyoz6swey` in the lockfile.
The original registry integrity remains associated with 5.3.1. Record this as a
locally modified dependency rather than a published fixed version.

### Regression checks and maintenance

Run `node --test --test-concurrency=1 scripts/ci/basic-ftp-backport.test.cjs`
on both supported Node runtimes. Its fixtures exercise normal Unix/DOS/MLSD
listings, raw versus reliable dates, permissions, links, name boundaries,
malformed lines and both LHCI/browser get-uri dependency closures. Actual
get-uri code runs with a mocked Client to preserve access options, MDTM/LIST
fallback, cache/not-found/error behavior, stream content and closure. No server
or listener is needed. Two adversarial parser cases run in children with a
2-second termination deadline and inputs below 300KiB, preventing an incomplete
backport from monopolizing the test process.

Use cleared environments and offline network/service guards. Frozen strict-peer
installation with lifecycle scripts ignored must apply the patch. Verify all
other installed basic-ftp files against 5.3.1 and all lockfile package metadata,
versions, importers and unrelated peer contexts against the reviewed base.
Retain existing workspace tests and their timeouts. Do not install hooks or
change performance, security, payment or release gates for this repair.

Treat the patch as locally maintained. On every dependency/lock update, review
patch applicability, consumer resolution, the installed module hashes and new
upstream security fixes; rerun the regressions. A missing or inapplicable patch
must fail rather than silently disappear. Remove it only when a published
in-range fixed release or a separately reviewed supported LHCI upgrade replaces
it. Preserve provenance and notices when adapting its tests or retiring it.

Audit remains blocked by the unchanged version ranges. Pnpm's audit request
reports package names/versions and original integrity, not the patch contents as
a remediation attestation. No fake version, major override, new exception or
audit-policy change is part of this patch.

### Retained notices

The installed package retains its original `LICENSE.txt` unchanged. The parser
comments continue to attribute their Apache Commons Net derivation under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). The patch
preserves those comments; it does not remove or relabel the upstream attribution.

Listing fixtures adapted from the official fix's `test/parseListSpec.js` retain
the upstream attribution. The upstream MIT notice is reproduced here:

> Copyright (c) 2019 Patrick Juchli
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.
