# Frontend deployment plane

Browser API origin selection is **build-time** and fail-closed.

`VERCEL_ENV` is not a `NEXT_PUBLIC_*` variable. Next.js inlines `NEXT_PUBLIC_*`
and `NODE_ENV` into client bundles; `process.env.VERCEL_ENV` is not reliably
present in the browser. Do not use it to distinguish Production from Preview
in frontend code.

## Required build variable

```
NEXT_PUBLIC_DEPLOYMENT_PLANE=production|staging|preview|development
```

Set this on every Customer, Vendor, and Admin Vercel project **before**
`next build`. Changing it requires a rebuild.

| Plane                 | Frontend                                     | Allowed API origin                                           | Rejected                                                   |
| --------------------- | -------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------- |
| `production`          | Production Vercel                            | `https://api.vergeo5.com` (default if URL unset)             | loopback, `https://api.staging.vergeo5.com`, unknown hosts |
| `staging` / `preview` | Staging branch Preview and protected Preview | `https://api.staging.vergeo5.com` (default if URL unset)     | loopback, `https://api.vergeo5.com`, unknown hosts         |
| `development`         | local `next dev` only                        | `http://localhost:8000` (or explicit loopback / staging API) | production API                                             |
| unset / unknown       | any                                          | none (`null`)                                                | everything — never infer local from missing config         |

Customer/Vendor read `NEXT_PUBLIC_API_BASE_URL`. Admin reads
`NEXT_PUBLIC_VERGEO_API_URL`.

There is no emergency override that lets Production use the staging API or
Preview use the production API.

## Operator checklist (do not deploy from this task)

1. Production Customer + Vendor: `NEXT_PUBLIC_DEPLOYMENT_PLANE=production` and
   `NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com`.
2. Production Admin: `NEXT_PUBLIC_DEPLOYMENT_PLANE=production` and
   `NEXT_PUBLIC_VERGEO_API_URL=https://api.vergeo5.com`.
3. Staging/Preview (all three): `NEXT_PUBLIC_DEPLOYMENT_PLANE=staging` or
   `preview`, API URL `https://api.staging.vergeo5.com`.
4. `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` remains unset/false until Google is
   explicitly enabled and verified.
5. Rebuild after setting the variables. Runtime-only env changes do not
   update an existing bundle.

## CI guard

`scripts/ci/check-no-loopback-api.mjs --require-affected --filter=...[base]`

- Unrelated changes with no customer/vendor/admin turbo tasks: pass.
- Affected frontend missing `.next`: fail.
- Loopback `:8000` origin in deployable JS: fail.
- Preview/staging bundle or env targeting `https://api.vergeo5.com`: fail.
- Production bundle or env targeting `https://api.staging.vergeo5.com`: fail.
