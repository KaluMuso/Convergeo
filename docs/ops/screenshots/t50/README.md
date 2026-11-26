# T50 Batch C — customer visual consistency

Captured against loopback fixture backend (`docs/ops/screenshots/harness/mock-backend.mjs`) with `pnpm dev` (customer on :3000). Viewports **360×900** and **1440×900**, light theme, WebP.

| File        | Route                 |
| ----------- | --------------------- |
| `vendors-*` | `/en/vendors`         |
| `events-*`  | `/en/events`          |
| `search-*`  | `/en/search?q=laptop` |
| `home-*`    | `/en`                 |

Regenerate: `node docs/ops/screenshots/t50/capture.mjs` (with customer dev + fixture env from harness README).
