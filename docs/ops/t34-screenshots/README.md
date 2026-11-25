# T34 admin polish — screenshots

Captured on the cloud agent VM against `pnpm --filter admin dev` (port 3002).

| File                                  | Viewport | Theme | Route                   |
| ------------------------------------- | -------- | ----- | ----------------------- |
| `login-desktop-light.png`             | 1280×900 | light | `/en/login`             |
| `login-mobile-light.png`              | 360×800  | light | `/en/login`             |
| `login-desktop-dark.png`              | 1280×900 | dark  | `/en/login`             |
| `login-mobile-dark.png`               | 360×800  | dark  | `/en/login`             |
| `permission-denied-desktop-light.png` | 1280×900 | light | `/en/permission-denied` |
| `permission-denied-mobile-light.png`  | 360×800  | light | `/en/permission-denied` |

Authenticated board routes (dashboard, KYC, orders, config hub, moderation hub) need Cloudflare Access + Supabase session; verify on staging after merge. Shell chrome (coloured nav icons, ⌘K palette, density toggle, `PageHeader`, `StatCard`, hub cards) is shared on every signed-in route.
