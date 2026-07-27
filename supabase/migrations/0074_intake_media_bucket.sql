-- M18-P03 — private storage bucket for quarantined intake media (D35).
--
-- Intake images stay PRIVATE until a human approves them. They are not public
-- listing media and never touch the Cloudinary path (routers/media.py), which
-- serves published product images.
--
-- Writes are service-role only: the vendor never uploads here directly. The
-- platform fetches server-side from WAHA, verifies magic bytes and a pixel
-- budget, strips EXIF, and only then persists. See app/services/intake/media.py.
--
-- Path convention: intake/{vendor_id}/{session_id}/{content_hash}
-- The vendor_id segment is what the ownership policy keys on.
--
-- ---------------------------------------------------------------------------
-- WHY THIS WHOLE FILE IS GUARDED
-- ---------------------------------------------------------------------------
-- `storage.buckets` / `storage.objects` are created by the Supabase storage
-- service, not by Postgres. Several CI jobs (migration replay, money DB-trigger
-- integration, COD container smoke) replay migrations against a PLAIN
-- pgvector/Postgres image with no storage schema at all, so an unguarded
-- reference here fails the entire replay with:
--
--     ERROR: relation "storage.buckets" does not exist
--
-- The repo's existing private bucket (`kyc-docs`, M12-P02b) sidesteps this by
-- being provisioned out-of-band and never appearing in a migration — which
-- works, but leaves its access policies undocumented in version control.
--
-- This file keeps the policies reviewable and diffable while staying replay-safe:
-- on a real Supabase database it provisions the bucket and its policies; on a
-- bare Postgres it is a deliberate no-op. Idempotent either way.
--
-- Reversible: drop the three policies and delete the bucket row.

do $$
begin
  if to_regclass('storage.buckets') is null then
    raise notice 'M18-P03: storage schema absent (bare Postgres) — skipping intake media bucket';
    return;
  end if;

  -- Private bucket. `public = false` is the whole point: nothing here is ever
  -- served by URL, and no anon role can enumerate it.
  insert into storage.buckets (id, name, public)
  values ('vendor-intake-media', 'vendor-intake-media', false)
  on conflict (id) do nothing;

  if to_regclass('storage.objects') is null then
    return;
  end if;

  -- Owning vendor may read its own objects. Path is
  -- intake/{vendor_id}/{session_id}/{hash}, so foldername()[2] is the vendor.
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'intake media owner read'
  ) then
    execute $policy$
      create policy "intake media owner read"
        on storage.objects
        for select
        to authenticated
        using (
          bucket_id = 'vendor-intake-media'
          and exists (
            select 1
            from public.vendors v
            where v.owner_user_id = (select auth.uid())
              and (storage.foldername(name))[2] = v.id::text
          )
        )
    $policy$;
  end if;

  -- Admin may read anything in the bucket (review queue, M18-P06).
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'intake media admin read'
  ) then
    execute $policy$
      create policy "intake media admin read"
        on storage.objects
        for select
        to authenticated
        using (
          bucket_id = 'vendor-intake-media'
          and public.has_role('admin')
        )
    $policy$;
  end if;

  -- No INSERT/UPDATE/DELETE policy for any client role: the service role
  -- (which bypasses RLS) is the only writer. anon gets nothing at all.
end
$$;
