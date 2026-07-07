# @vergeo/types

Generated Supabase database types for Vergeo5.

## `pnpm gen:types` (placeholder)

Once the Supabase pipeline lands (M03-P10), type generation will run via:

```bash
pnpm gen:types
```

That script will invoke the Supabase CLI (`supabase gen types typescript`) and write output to `packages/types/src/db.ts`, which this package will re-export.

Until then, `src/index.ts` exposes a minimal `Database` placeholder so downstream packages can import `@vergeo/types` without drift.
