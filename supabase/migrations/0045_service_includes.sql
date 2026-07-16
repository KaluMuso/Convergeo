-- 0045: "What's included" for services.
--
-- Service listings carry a prose `description` but no structured list of what the
-- service actually includes (deliverables / scope bullets). This adds that as a
-- text array so the service detail page can show a "What's included" checklist
-- and the vendor can edit it as one-per-line bullets.
--
-- Additive with a NOT NULL default of the empty array (constant default — no table
-- rewrite): existing services get `{}` and simply render no checklist. Inherits
-- the services table RLS — no policy change.
--
-- Reversible: `alter table public.services drop column includes;`

alter table public.services
  add column if not exists includes text[] not null default '{}';

comment on column public.services.includes is
  'Ordered "what''s included" bullet points for the service detail page. Empty array until set.';
