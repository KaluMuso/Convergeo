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
-- The vendor_id prefix is what the ownership policy keys on.
--
-- Reversible: delete the policies and the bucket row.

insert into storage.buckets (id, name, public)
values ('vendor-intake-media', 'vendor-intake-media', false)
on conflict (id) do nothing;

-- Owning vendor may read its own objects (path prefix intake/{vendor_id}/...).
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
  );

-- Admin may read anything in the bucket (review queue, M18-P06).
create policy "intake media admin read"
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'vendor-intake-media'
    and public.has_role('admin')
  );

-- No INSERT/UPDATE/DELETE policy for any client role: the service role (which
-- bypasses RLS) is the only writer. anon gets nothing at all.
