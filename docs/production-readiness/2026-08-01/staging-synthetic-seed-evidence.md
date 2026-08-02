# Staging synthetic seed evidence — 2026-08-01

## Scope

This record applies only to the isolated `vergeo-sandbox` Supabase project and
the `staging` GitHub branch. It does not describe production.

## STG-01 result

GitHub Actions **Deploy staging #14** completed successfully on 2026-08-01
with the synthetic seed enabled and Vercel preview intentionally skipped.

The completed jobs were:

- environment separation;
- Supabase migrations, schema/RLS checks, and synthetic seed;
- SHA-tagged API image build;
- OCI staging API deployment;
- staging smoke/evidence; and
- no-production-promotion guard.

The following staging-only fixture counts were read after the run:

| Fixture type | Count |
| --- | ---: |
| Synthetic Auth users | 6 |
| Synthetic profiles | 6 |
| Synthetic vendors | 3 |
| Synthetic KYC records | 2 |
| Synthetic categories/products/listings | 0 |

No production records, orders, payments, ledger transactions, private KYC
objects, payment credentials, or public-production catalogue records were
created.

## Next controlled change

STG-SEED-02 adds the single reserved
`stg-rv-20260719-list-prd` category/product/listing fixture. It must remain
staging-only, tagged with the reserved prefix, owned by the approved synthetic
vendor, priced in integer ngwee, tracked in stock, and free of media, orders
and payments. A successful staging deployment after its review is required
before it is used for search, cart, checkout or Lenco sandbox drills.
