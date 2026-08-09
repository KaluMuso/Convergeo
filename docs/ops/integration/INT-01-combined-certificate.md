# INT-01 Combined Integration Certificate

**Status:** REHEARSAL ONLY — DO NOT MERGE THIS BRANCH TO MASTER  
**Generated:** 2026-08-09  
**Temporary integration SHA:** `601fc6cd8efa6d49e0e8a1747a7b0c5db2aa4b71`  
**Base master:** `a57306d9e22067866af30341bf0e86f18bde4f74` (#603)

## Merge sequence (serial)

1. #604 @ `3ad167ea82d3`
2. #606 @ `99b5fa9a65ef`
3. #605 @ `2a44284003ee`
4. #607 @ `1db2b70d0d19`
5. #608 @ `35bc91a1a030`
6. #609 @ `8215139fdeb8`

## Conflict outcomes

| Hotspot               | Result                          |
| --------------------- | ------------------------------- |
| catalog.json locales  | Deep-merged 607+608             |
| ratelimit_policies.py | Combined 607+609                |
| PDP files             | Combined report + Modal/JSON-LD |

## Stale PRs

- #600 STALE docs draft
- #601 SUPERSEDED by #607+#608+#609 — MUST NOT MERGE
- #602 SUPERSEDED by #604 — MUST NOT MERGE

## Non-actions

Not merged to master. Not deployed. No production mutations.
