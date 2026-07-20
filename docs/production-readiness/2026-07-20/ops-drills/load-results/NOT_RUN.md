# Load test results — NOT_RUN (2026-07-20)

Required profile: **100 concurrent users** against approved test target.

| Field                 | Value              |
| --------------------- | ------------------ |
| p50                   | n/a                |
| p95                   | n/a                |
| p99                   | n/a                |
| Throughput            | n/a                |
| HTTP error rate       | n/a                |
| Database errors       | n/a                |
| Queue/workflow errors | n/a                |
| Invariant check       | NOT_RUN            |
| Real provider charges | **none** (refused) |

Documented targets (unchanged):

- Checkout: `p95<500` @ 100 VUs
- Browse: search/plp `p95<400`, suggest `p95<250`
- `http_req_failed rate<0.01`

**Verdict: FAIL** for LIVE-11. Thresholds not altered after seeing the (absent) result.
