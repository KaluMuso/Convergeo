# Cross-app build inputs (Turborepo) — stale-build repair

## The failure this prevents

`apps/vendor` and `apps/admin` render the Customer app's shared authentication
presentation components through **relative cross-app imports**:

```
apps/vendor -> ../../../../../customer/app/[locale]/(auth)/_components/{login-shell, otp-form, auth-utils, auth-labels}
apps/admin  -> ../../../../../customer/app/[locale]/(auth)/_components/{login-shell, auth-labels}
```

Neither app declares a dependency on `customer` — it is an app, not a workspace
package, so there is nothing to declare. Turborepo therefore hashed
`vendor#build` from `apps/vendor/**` plus its declared internal dependencies
only, and a change confined to `apps/customer/**` left that hash untouched.

Staging E2E run #74 is the worked example. PR #697 changed only
`apps/customer/app/[locale]/(auth)/_components/{phone-form,login-shell,auth-utils}`,
and the Vercel build log for the Vendor deployment of the merge commit read:

```
vendor:build: cache hit, replaying logs b0a9df56536e2d5e
```

— the identical task hash the pre-#697 staging deployment had produced. The
build output was byte-identical, so the deployed Vendor app never received the
fix, while the E2E identity probe still reported `shaVerified: true` and
`buildIdPrefix: d92cec06defd`. **The `/health` SHA cannot detect this**: it
comes from the deployment's git metadata, not from the compiled bundle.

The last commit that actually rebuilt the Vendor app was `0fed3cf4` (#693,
2026-09-03) — the last change to `apps/vendor/**` or `packages/**`. Everything
the shared components gained after that (#695's OTP single-flight lock, #697's
`next` forwarding) was missing from the deployed portal.

## The repair (this phase — deliberately temporary)

`apps/vendor/turbo.json` and `apps/admin/turbo.json`:

```json
{
  "$schema": "https://turbo.build/schema.json",
  "extends": ["//"],
  "tasks": {
    "build": {
      "inputs": ["$TURBO_DEFAULT$", "$TURBO_ROOT$/apps/customer/app/**"]
    }
  }
}
```

- `$TURBO_DEFAULT$` keeps the app's own sources in the hash. Declaring an
  external glob **without** it would silently drop them.
- `$TURBO_ROOT$/apps/customer/app/**` is root-relative (Turborepo ≥ 2.1;
  this repo pins 2.10.9).
- The glob is deliberately broader than the shared-auth directory alone. The
  real path contains the literal segments `[locale]` and `(auth)`, which are
  glob metacharacters; a narrower pattern would depend on escaping rules whose
  failure mode is **silent under-matching** — precisely the bug being fixed.
  Over-invalidation only costs an extra ~20s Vendor build.
- Scoped to the two importing apps. The root `build` task keeps no `inputs`, so
  no other workspace build is re-hashed.
- `dependsOn: ["^build"]` and the root `outputs` stay inherited via
  `extends: ["//"]`.

`scripts/qa/self-test/turbo-cross-app-inputs.test.mjs` enforces the contract in
ordinary CI: it discovers cross-app imports from source and requires each
importing app to declare a `$TURBO_ROOT$` glob covering what it imports.

## Durable follow-up — NOT implemented in this phase

Extract the shared authentication presentation components into a real workspace
package, e.g. `packages/auth-ui`, and have `apps/{customer,vendor,admin}`
depend on it normally.

Turborepo would then derive the dependency graph correctly from
`package.json`, with no cross-app source globs to keep in sync, and the guard
above could be reduced to "no app imports another app's source at all". That is
the preferred end state; the input globs here are the minimal, diagnostic
repair that unblocks the run #74 investigation.
