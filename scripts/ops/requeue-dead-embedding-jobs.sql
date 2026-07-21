-- Requeue embedding jobs killed by provider/config failures so the semantic
-- lane can drain after OPENROUTER_API_KEY is set on the API host.
--
-- Safe to re-run. Does not touch jobs already `done`.
-- Prefer after deploying the fail-closed tick (skips claim when key missing).

begin;

update public.embedding_jobs
set
  status = 'queued',
  attempts = 0,
  last_error = null,
  updated_at = timezone('utc', now())
where status = 'dead'
  and (
    last_error ilike '%OPENROUTER_API_KEY%'
    or last_error = 'Primary and fallback embedding providers failed'
  );

commit;

-- Verify:
-- select status, count(*) from public.embedding_jobs group by 1;
-- select count(*) filter (where embedding is null) from public.search_documents;
