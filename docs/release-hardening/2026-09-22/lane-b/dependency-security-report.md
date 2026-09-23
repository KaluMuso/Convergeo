# Lane B dependency/security report

Status: **REPAIR_REQUIRED**

This candidate removes every currently patchable critical/high dependency finding discovered from the exact S3 candidate. Two high `extract-zip` advisories remain in the development-only Lighthouse CI toolchain, have no patched `extract-zip` release, and require an explicit reviewer/user risk decision. This implementation does not create or approve that exception.

## Scope and provenance

- Repository: `KaluMuso/Convergeo`
- Branch: `hardening/20260922-b-security-deps`
- Exact root/start: `2b067aeb72dd5145835ab9b6ee000d603e8dbd73`
- Start tree: `105719dd5a3ce7510a73600587b72a004d5819fa`
- Master comparator: `287d6885a806514b7ddbb73f7b779f8be2d53f14`
- Existing remediation inspected: `07eebc6c563d85fa6d2458099d39890703d2b553` (diverged; not cherry-picked)
- Master CI evidence: run `35700777653`, dependency job `106657992736`
- Exact Node toolchain: Node `22.23.2`, npm `10.9.8`, pnpm `9.15.4`
- Exact Python toolchain: CPython `3.12.12`, uv `0.9.30`, pip-audit `2.10.1`
- Raw local evidence export: `lane-b-security-deps-export-20260922T110458Z`

## Missing from master versus already in S3

| Finding/change              | Master                                             | Exact S3                                                     | Lane B delta                                                                               |
| --------------------------- | -------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Next.js critical advisories | `next@15.5.23` vulnerable                          | package floors `^15.5.24`; lock resolves `15.5.25`           | None; verified existing S3 repair                                                          |
| `browserslist` highs        | `4.28.6`                                           | override/resolution `4.28.8`                                 | None; verified existing S3 repair                                                          |
| `fast-uri` highs            | `3.1.5`                                            | override/resolution `3.1.6`                                  | None; verified existing S3 repair                                                          |
| `js-yaml` high              | `3.15.1` and `4.3.1`                               | overrides `3.15.2` and `4.3.2`                               | None; verified existing S3 repair                                                          |
| `sharp` high                | `0.35.0`                                           | override/resolution `0.35.4`                                 | None; verified existing S3 repair                                                          |
| `postcss` override          | older vulnerable range                             | `8.5.23`                                                     | None; S3 is newer than remediation commit's `8.5.18`                                       |
| `tmp` high                  | `0.0.33` and `0.1.0` through `@lhci/cli`           | still present                                                | overrides both exact vulnerable versions to `0.2.7`                                        |
| Python audit                | skipped by master CI after Node failure            | `anyio@4.14.1`, `cryptography@49.0.0`, `h2@4.3.0` vulnerable | lock to minimum fixed `4.14.2`, `50.0.0`, `4.4.1`                                          |
| `extract-zip` highs         | `2.0.1` through LHCI                               | still present                                                | no code workaround or safe compatible upgrade; explicit risk decision remains required     |
| Audit parser                | shell parser can mask command failure/empty output | unchanged                                                    | fail-closed Node parser plus six negative/positive self-tests; CI wiring belongs to Lane C |

## Blocking advisory disposition

| Advisory                                                                                   | Installed path/version                                                                                               | Fixed/removal option                                                                               | Runtime and ownership                                                                                  | Breaking-change assessment                                                                   | Disposition                                          |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `GHSA-p293-qw3h-jr36`, `GHSA-2xp9-vwfh-vxw4`                                               | all three apps and shared packages, `next@15.5.23` on master                                                         | `>=15.5.24`                                                                                        | production framework/runtime                                                                           | patch update only                                                                            | Already repaired in S3; lock resolves `15.5.25`      |
| `GHSA-c83g-rgw3-j3cx`, `GHSA-73wf-gq98-2v4g`                                               | customer Serwist build chain, `browserslist@4.28.6`                                                                  | `>=4.28.7`                                                                                         | build dependency, not shipped executable runtime                                                       | patch override                                                                               | Already repaired in S3 at `4.28.8`                   |
| `GHSA-5jgf-p345-68v8`, `GHSA-f65p-4m7j-42xc`, `GHSA-fph4-wmhf-6fwf`, `GHSA-jqff-g426-hqxp` | AJV/tool and webpack chains, `fast-uri@3.1.5`                                                                        | `>=3.1.6`                                                                                          | mixed build/tool transitive dependency                                                                 | patch override                                                                               | Already repaired in S3 at `3.1.6`                    |
| `GHSA-2883-xcg3-v3hh`                                                                      | LHCI `3.15.1`; lint/config chains `4.3.1`                                                                            | `3.15.2`, `4.3.2`                                                                                  | development/CI only                                                                                    | patch overrides                                                                              | Already repaired in S3                               |
| `GHSA-rgj7-g3m4-5g8c`                                                                      | Next image chain, `sharp@0.35.0`                                                                                     | `>=0.35.4`                                                                                         | production image runtime                                                                               | patch override                                                                               | Already repaired in S3 at `0.35.4`                   |
| `GHSA-ph9p-34f9-6g65`                                                                      | `@lhci/cli@0.15.1 -> inquirer -> external-editor -> tmp@0.0.33` and direct LHCI `tmp@0.1.0`                          | `>=0.2.6`                                                                                          | root dev/CI dependency; not bundled                                                                    | patch override; API-compatible in validation                                                 | Repaired here at `0.2.7`; no exception               |
| `GHSA-jmr9-qjv8-65gv`                                                                      | `@lhci/cli@0.15.1 -> lighthouse@12.6.1 -> puppeteer-core@24.43.1 -> @puppeteer/browsers@2.13.2 -> extract-zip@2.0.1` | no patched `extract-zip`; removal requires LHCI to take a Lighthouse/Puppeteer chain that drops it | root dev/CI only; used while obtaining Chrome for Lighthouse, not application/API runtime              | forcing parent majors would bypass LHCI's exact pins and is not a compatible residual repair | **Open high; proposed exception only, not approved** |
| `GHSA-7pqw-9j4j-h8q3`                                                                      | same chain, `extract-zip@2.0.1`                                                                                      | no patched release                                                                                 | same development-only reachability; archive extraction is the affected operation                       | same parent-major incompatibility                                                            | **Open high; proposed exception only, not approved** |
| `CVE-2026-63374` / `GHSA-82r6-8w77-94w6`                                                   | `anyio@4.14.1` via FastAPI/Starlette, HTTPX/Supabase and Uvicorn/watchfiles                                          | `4.14.2`                                                                                           | production API transitive dependency                                                                   | patch update                                                                                 | Repaired here at `4.14.2`                            |
| `CVE-2026-64847` / `GHSA-5p39-cfhj-2xmp`                                                   | same `anyio@4.14.1` chain                                                                                            | `4.14.2`                                                                                           | production dependency; process-pool exploitability depends on use of attacker-influenced worker stderr | patch update                                                                                 | Repaired here at `4.14.2`                            |
| `CVE-2026-63349` / `GHSA-3w57-8xmc-8v26`                                                   | same `anyio@4.14.1` chain                                                                                            | `4.14.2`                                                                                           | production dependency; POSIX subprocess privilege-dropping flaw                                        | patch update                                                                                 | Repaired here at `4.14.2`                            |
| `CVE-2026-69247` / `GHSA-g6cj-pr64-35w5`                                                   | `supabase -> supabase-auth[crypto] -> pyjwt[crypto] -> cryptography@49.0.0`                                          | `50.0.0`                                                                                           | production API transitive dependency; PKCS#7 oracle needs attacker-supplied adaptive decrypt service   | major update; upstream change is targeted security fix, regression suite required            | Repaired here at minimum fixed `50.0.0`              |
| `CVE-2026-71554` / `GHSA-6hr6-w5qg-qmwg`                                                   | `supabase/httpx[http2] -> h2@4.3.0`                                                                                  | `4.4.1`                                                                                            | production HTTP/2 transitive dependency; duplicate Host request-smuggling primitive                    | minor update                                                                                 | Repaired here at `4.4.1`                             |

The Python advisories are treated as runtime-applicable because all three packages are in production dependency paths, even where this codebase does not currently expose the advisory's narrower exploit precondition.

## Audit outcomes

- Master Node isolated audit: `2 critical`, `13 high`, `8 moderate`, `2 low` occurrences.
- Exact S3 Node isolated audit: `0 critical`, `4 high`, `7 moderate`, `2 low` occurrences.
- Lane B Node audit: `0 critical`, `2 high`, `7 moderate`, `0 low`; only the two unpatched `extract-zip` advisories remain.
- Master/S3 Python audit: five unique advisories across `anyio`, `cryptography`, and `h2` (duplicate records are caused by extras in the exported dependency graph).
- Lane B Python audit: zero known vulnerabilities.
- Standalone `e2e/package-lock.json`: unchanged blob `2be30aea6ae23c5d27f6a5211f996cbd6811ed40`; clean install and audit found zero vulnerabilities.

Moderate Node findings remain in development/CI chains (`vitest`/`@vitest/mocker`, `qs`, and `uuid`). They are recorded, not hidden, and do not meet the repository's high/critical blocking threshold. The Vitest repair requires a major from `3.2.7` to `>=4.1.11`; it should be handled as a separately tested tooling upgrade.

## Lockfile effect

- `pnpm-lock.yaml`: only the two vulnerable LHCI `tmp` resolutions collapse to `tmp@0.2.7`; the standalone E2E lockfile is untouched.
- `services/api/uv.lock`: `anyio 4.14.1 -> 4.14.2`, `cryptography 49.0.0 -> 50.0.0`, and `h2 4.3.0 -> 4.4.1`; no audit tooling is added to application dependencies.
- Frozen Node and Python installs are required and locally exercised.

## Remaining risk decision

No accepted exception is added by Lane B. If a reviewer elects to accept the two `extract-zip` findings temporarily, the decision must name a security owner, acknowledge both GHSA IDs and the exact LHCI chain, limit the scope to CI/dev use, require trusted Chrome download provenance, set an expiry/review date, and remove the exception when `@lhci/cli` adopts a Lighthouse/Puppeteer chain without `extract-zip`. Until then the disposition remains `REPAIR_REQUIRED`.

Hosted CI and independent review are `NOT_RUN`; publication is outside this packet.
