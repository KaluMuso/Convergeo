-- Ask Vergeo answer log + auditor findings.
--
-- Every Ask Vergeo answer shown to a customer is recorded (question, answer text,
-- model, source, cited entities with the price that was shown, who asked, locale)
-- so an after-the-fact auditor can compare what the assistant said with what the
-- marketplace actually sells. The auditor (app/services/ask/audit.py) runs
-- deterministic checks only (price mismatch, implausible price, missing or
-- inactive entity, vendor mismatch), writes one finding row per problem and flips
-- ask_answers.audit_status to 'flagged'. That flip raises one in-app admin
-- notification through the existing notification center.
--
-- Reuse note: ask_usage stores only a question hash (quota accounting) and
-- ask_cache is keyed by query and user-agnostic, so neither can hold a per-answer
-- record. These are new tables; nothing existing is altered.
--
-- RLS: admins read everything, a customer reads only answers they asked, the
-- findings are admin-only. All writes are service-role only (no client grants).
--
-- Additive only. Reversible:
--   DROP TRIGGER IF EXISTS ask_answers_flag_notify ON public.ask_answers;
--   DROP FUNCTION IF EXISTS private.ask_answer_flag_notify();
--   DROP TABLE IF EXISTS public.ask_answer_findings;
--   DROP TABLE IF EXISTS public.ask_answers;

-- ---------------------------------------------------------------------------
-- ask_answers
-- ---------------------------------------------------------------------------
create table public.ask_answers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users (id) on delete set null,
  guest_key text,
  locale text check (locale is null or char_length(locale) <= 16),
  query text not null check (char_length(query) between 1 and 500),
  answer_text text not null check (char_length(answer_text) <= 8000),
  model text check (model is null or char_length(model) <= 120),
  source text not null check (source in ('ai', 'workflow', 'fallback')),
  intent text check (intent is null or char_length(intent) <= 60),
  cached boolean not null default false,
  refused boolean not null default false,
  -- [{kind, id, title, price_ngwee, price_max_ngwee, vendor_id, slug}] as shown.
  citations jsonb not null default '[]'::jsonb
    check (jsonb_typeof(citations) = 'array'),
  audit_status text not null default 'pending'
    check (audit_status in ('pending', 'passed', 'flagged', 'error')),
  audit_severity text check (audit_severity in ('info', 'warning', 'critical')),
  audited_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  check (user_id is not null or guest_key is not null)
);

create index ask_answers_created_idx
  on public.ask_answers (created_at desc, id desc);

create index ask_answers_flagged_idx
  on public.ask_answers (created_at desc, id desc)
  where audit_status = 'flagged';

create index ask_answers_pending_idx
  on public.ask_answers (created_at)
  where audit_status = 'pending';

create index ask_answers_user_idx
  on public.ask_answers (user_id, created_at desc)
  where user_id is not null;

comment on table public.ask_answers is
  'Ask Vergeo answer log: what a customer was shown, with cited entities and the audit verdict. Service-role writes only.';

alter table public.ask_answers enable row level security;
alter table public.ask_answers force row level security;

create policy ask_answers_select_own_or_admin
  on public.ask_answers
  for select
  to authenticated
  using (user_id = (select auth.uid()) or public.has_role('admin'));

revoke all on public.ask_answers from public, anon, authenticated;
grant select on public.ask_answers to authenticated;
grant all on public.ask_answers to service_role;

-- ---------------------------------------------------------------------------
-- ask_answer_findings
-- ---------------------------------------------------------------------------
create table public.ask_answer_findings (
  id uuid primary key default gen_random_uuid(),
  answer_id uuid not null references public.ask_answers (id) on delete cascade,
  rule text not null check (rule ~ '^[a-z][a-z0-9_]{1,62}$'),
  severity text not null check (severity in ('info', 'warning', 'critical')),
  reason text not null check (char_length(reason) between 1 and 600),
  entity_kind text check (
    entity_kind is null
    or entity_kind in ('product', 'listing', 'service', 'event', 'vendor')
  ),
  entity_id uuid,
  vendor_id uuid references public.vendors (id) on delete set null,
  details jsonb not null default '{}'::jsonb
    check (jsonb_typeof(details) = 'object'),
  created_at timestamptz not null default timezone('utc', now())
);

create index ask_answer_findings_answer_idx
  on public.ask_answer_findings (answer_id);

create index ask_answer_findings_vendor_idx
  on public.ask_answer_findings (vendor_id, created_at desc)
  where vendor_id is not null;

comment on table public.ask_answer_findings is
  'Deterministic auditor findings for logged Ask Vergeo answers (admin-only).';

alter table public.ask_answer_findings enable row level security;
alter table public.ask_answer_findings force row level security;

create policy ask_answer_findings_select_admin
  on public.ask_answer_findings
  for select
  to authenticated
  using (public.has_role('admin'));

revoke all on public.ask_answer_findings from public, anon, authenticated;
grant select on public.ask_answer_findings to authenticated;
grant all on public.ask_answer_findings to service_role;

-- ---------------------------------------------------------------------------
-- Admin notification when an answer is flagged (one per answer).
-- Uses the notification center's admin fan-out; a failure here must never
-- roll back the audit write, so it is downgraded to a WARNING.
-- ---------------------------------------------------------------------------
create or replace function private.ask_answer_flag_notify()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
begin
  perform private.enqueue_admin_in_app_notification(
    'vendors.manage',
    'ask_answer_flagged',
    jsonb_build_object('severity', coalesce(new.audit_severity, 'warning')),
    '/ask-audit',
    'ask_answer_flagged:' || new.id::text
  );
  return null;
exception
  when others then
    raise warning 'ask_answer_flag_notify skipped (sqlstate %): %', sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.ask_answer_flag_notify() from public, anon, authenticated;

create trigger ask_answers_flag_notify
  after update of audit_status on public.ask_answers
  for each row
  when (new.audit_status = 'flagged' and old.audit_status is distinct from 'flagged')
  execute function private.ask_answer_flag_notify();
