-- M03-P03: Services (RFQ) and events (ticketing) data core.
-- Quote privacy: providers must never read rival quotes on the same job.
-- tickets.order_item_id is a bare nullable uuid; FK to order_items lands in 0005_orders.sql (M03-P04).

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.services (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  category text not null,
  title text not null,
  description text,
  service_area text,
  from_price_ngwee bigint check (from_price_ngwee is null or from_price_ngwee > 0),
  portfolio_images text[] not null default '{}',
  status text not null default 'draft'
    check (status in ('draft', 'active', 'paused')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index services_vendor_id_idx on public.services (vendor_id);
create index services_status_idx on public.services (status);
create index services_category_idx on public.services (category);

create trigger services_set_updated_at
  before update on public.services
  for each row
  execute function public.set_updated_at();

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references auth.users (id) on delete cascade,
  category text not null,
  description text not null,
  preferred_date date,
  budget_band_min_ngwee bigint check (budget_band_min_ngwee is null or budget_band_min_ngwee > 0),
  budget_band_max_ngwee bigint check (budget_band_max_ngwee is null or budget_band_max_ngwee > 0),
  status text not null default 'open'
    check (status in ('open', 'quoted', 'accepted', 'completed', 'cancelled')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint jobs_budget_band_order_chk check (
    budget_band_min_ngwee is null
    or budget_band_max_ngwee is null
    or budget_band_min_ngwee <= budget_band_max_ngwee
  )
);

create index jobs_customer_id_idx on public.jobs (customer_id);
create index jobs_status_idx on public.jobs (status);
create index jobs_category_idx on public.jobs (category);
create index jobs_open_status_idx on public.jobs (status) where status = 'open';

create trigger jobs_set_updated_at
  before update on public.jobs
  for each row
  execute function public.set_updated_at();

create table public.job_quotes (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs (id) on delete cascade,
  provider_vendor_id uuid not null references public.vendors (id) on delete restrict,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  message text,
  status text not null default 'submitted'
    check (status in ('submitted', 'accepted', 'declined', 'expired')),
  expires_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint job_quotes_job_id_provider_vendor_id_key unique (job_id, provider_vendor_id)
);

create index job_quotes_job_id_idx on public.job_quotes (job_id);
create index job_quotes_provider_vendor_id_idx on public.job_quotes (provider_vendor_id);

create trigger job_quotes_set_updated_at
  before update on public.job_quotes
  for each row
  execute function public.set_updated_at();

create table public.events (
  id uuid primary key default gen_random_uuid(),
  organiser_vendor_id uuid not null references public.vendors (id) on delete restrict,
  title text not null,
  slug text not null unique,
  description text,
  venue text,
  lat double precision,
  lng double precision,
  images text[] not null default '{}',
  status text not null default 'draft'
    check (status in ('draft', 'published', 'cancelled', 'completed')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index events_organiser_vendor_id_idx on public.events (organiser_vendor_id);
create index events_status_idx on public.events (status);
create index events_published_slug_idx on public.events (slug) where status = 'published';

create trigger events_set_updated_at
  before update on public.events
  for each row
  execute function public.set_updated_at();

create table public.event_instances (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  starts_at timestamptz not null,
  capacity int not null check (capacity >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index event_instances_event_id_starts_at_idx
  on public.event_instances (event_id, starts_at);
create index event_instances_starts_at_idx on public.event_instances (starts_at);

create trigger event_instances_set_updated_at
  before update on public.event_instances
  for each row
  execute function public.set_updated_at();

create table public.ticket_types (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  kind text not null check (kind in ('fixed', 'tier', 'free_rsvp')),
  name text not null,
  price_ngwee bigint not null check (price_ngwee >= 0),
  qty_cap int check (qty_cap is null or qty_cap > 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint ticket_types_free_rsvp_price_chk check (
    (kind = 'free_rsvp' and price_ngwee = 0)
    or (kind <> 'free_rsvp' and price_ngwee > 0)
  )
);

create index ticket_types_event_id_idx on public.ticket_types (event_id);

create trigger ticket_types_set_updated_at
  before update on public.ticket_types
  for each row
  execute function public.set_updated_at();

create table public.tickets (
  id uuid primary key default gen_random_uuid(),
  instance_id uuid not null references public.event_instances (id) on delete restrict,
  ticket_type_id uuid not null references public.ticket_types (id) on delete restrict,
  holder_user_id uuid not null references auth.users (id) on delete restrict,
  -- Nullable link to commerce spine; FK to public.order_items added in 0005_orders.sql (M03-P04).
  order_item_id uuid,
  status text not null default 'issued'
    check (status in ('issued', 'checked_in', 'transferred', 'void')),
  qr_secret text,
  pin_hash text,
  checked_in_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index tickets_instance_id_status_idx on public.tickets (instance_id, status);
create index tickets_holder_user_id_idx on public.tickets (holder_user_id);

create trigger tickets_set_updated_at
  before update on public.tickets
  for each row
  execute function public.set_updated_at();

-- Ticket lifecycle transitions are server-controlled (issuance, check-in, transfer).
create or replace function public.guard_ticket_client_mutation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if tg_op = 'INSERT' then
    raise exception 'tickets are issued server-side only';
  end if;

  if tg_op = 'UPDATE' then
    if new.status is distinct from old.status
      or new.checked_in_at is distinct from old.checked_in_at
      or new.qr_secret is distinct from old.qr_secret
      or new.pin_hash is distinct from old.pin_hash
      or new.holder_user_id is distinct from old.holder_user_id
      or new.order_item_id is distinct from old.order_item_id then
      raise exception 'ticket status and secrets are server-controlled';
    end if;
  end if;

  if tg_op = 'DELETE' then
    raise exception 'tickets cannot be deleted by clients';
  end if;

  return new;
end;
$$;

create trigger tickets_guard_client_mutation
  before insert or update or delete on public.tickets
  for each row
  execute function public.guard_ticket_client_mutation();

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.services enable row level security;
alter table public.jobs enable row level security;
alter table public.job_quotes enable row level security;
alter table public.events enable row level security;
alter table public.event_instances enable row level security;
alter table public.ticket_types enable row level security;
alter table public.tickets enable row level security;

alter table public.services force row level security;
alter table public.jobs force row level security;
alter table public.job_quotes force row level security;
alter table public.events force row level security;
alter table public.event_instances force row level security;
alter table public.ticket_types force row level security;
alter table public.tickets force row level security;

-- services: public read active listings; vendor CRUD own; admin all.
create policy services_public_active_select
  on public.services
  for select
  using (status = 'active');

comment on policy services_public_active_select on public.services is
  'Anonymous and authenticated clients may read active service listings.';

create policy services_vendor_owner_select
  on public.services
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = services.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy services_vendor_owner_select on public.services is
  'Vendor owners may read their own services in any status.';

create policy services_vendor_owner_insert
  on public.services
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = services.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy services_vendor_owner_update
  on public.services
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = services.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = services.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy services_vendor_owner_delete
  on public.services
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = services.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy services_vendor_owner_insert on public.services is
  'Vendor owners may create services for vendors they own.';
comment on policy services_vendor_owner_update on public.services is
  'Vendor owners may update their own services.';
comment on policy services_vendor_owner_delete on public.services is
  'Vendor owners may delete their own services.';

create policy services_admin_all
  on public.services
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy services_admin_all on public.services is
  'Platform admins may manage every service row.';

-- jobs: customer owner full CRUD; matched active providers may read open jobs; admin all.
create policy jobs_customer_all
  on public.jobs
  for all
  to authenticated
  using (customer_id = (select auth.uid()))
  with check (customer_id = (select auth.uid()));

comment on policy jobs_customer_all on public.jobs is
  'RFQ customers may create, read, update, and delete their own jobs.';

create policy jobs_matched_provider_select
  on public.jobs
  for select
  to authenticated
  using (
    status = 'open'
    and exists (
      select 1
      from public.vendors v
      where v.owner_user_id = (select auth.uid())
        and v.status = 'active'
    )
  );

comment on policy jobs_matched_provider_select on public.jobs is
  'Active vendors may read open RFQ jobs (v1: category matching narrows results at the API layer in M11).';

create policy jobs_admin_all
  on public.jobs
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy jobs_admin_all on public.jobs is
  'Platform admins may manage every RFQ job.';

-- job_quotes: crown-jewel privacy — quoting provider, job customer, or admin only.
create policy job_quotes_provider_select
  on public.job_quotes
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = job_quotes.provider_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy job_quotes_provider_select on public.job_quotes is
  'A provider may read only quotes they submitted — never rival quotes on the same job.';

create policy job_quotes_customer_select
  on public.job_quotes
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.jobs j
      where j.id = job_quotes.job_id
        and j.customer_id = (select auth.uid())
    )
  );

comment on policy job_quotes_customer_select on public.job_quotes is
  'The RFQ customer may read every quote on their own job.';

create policy job_quotes_admin_all
  on public.job_quotes
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy job_quotes_admin_all on public.job_quotes is
  'Platform admins may manage every job quote.';

create policy job_quotes_provider_insert
  on public.job_quotes
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = job_quotes.provider_vendor_id
        and v.owner_user_id = (select auth.uid())
        and v.status = 'active'
    )
    and exists (
      select 1
      from public.jobs j
      where j.id = job_quotes.job_id
        and j.status = 'open'
    )
  );

comment on policy job_quotes_provider_insert on public.job_quotes is
  'Active vendors may submit quotes on open jobs; provider_vendor_id must be their own vendor.';

create policy job_quotes_provider_update
  on public.job_quotes
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = job_quotes.provider_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = job_quotes.provider_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy job_quotes_provider_update on public.job_quotes is
  'Quoting providers may update their own submitted quotes.';

-- events / instances / ticket_types: public read when published; organiser CRUD own; admin all.
create policy events_public_published_select
  on public.events
  for select
  using (status = 'published');

comment on policy events_public_published_select on public.events is
  'Anonymous and authenticated clients may read published events only.';

create policy events_organiser_select
  on public.events
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = events.organiser_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy events_organiser_insert
  on public.events
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = events.organiser_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy events_organiser_update
  on public.events
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = events.organiser_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = events.organiser_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy events_organiser_delete
  on public.events
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = events.organiser_vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy events_organiser_select on public.events is
  'Event organisers may read their events in any status.';
comment on policy events_organiser_insert on public.events is
  'Event organisers may create events for vendors they own.';
comment on policy events_organiser_update on public.events is
  'Event organisers may update their own events.';
comment on policy events_organiser_delete on public.events is
  'Event organisers may delete their own events.';

create policy events_admin_all
  on public.events
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy events_admin_all on public.events is
  'Platform admins may manage every event.';

create policy event_instances_public_published_select
  on public.event_instances
  for select
  using (
    exists (
      select 1
      from public.events e
      where e.id = event_instances.event_id
        and e.status = 'published'
    )
  );

comment on policy event_instances_public_published_select on public.event_instances is
  'Instances are public only when the parent event is published.';

create policy event_instances_organiser_select
  on public.event_instances
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_instances.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy event_instances_organiser_insert
  on public.event_instances
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_instances.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy event_instances_organiser_update
  on public.event_instances
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_instances.event_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_instances.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy event_instances_organiser_delete
  on public.event_instances
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_instances.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy event_instances_organiser_select on public.event_instances is
  'Organisers may read instances for their events regardless of publish status.';
comment on policy event_instances_organiser_insert on public.event_instances is
  'Organisers may create instances for events they own.';
comment on policy event_instances_organiser_update on public.event_instances is
  'Organisers may update instances for events they own.';
comment on policy event_instances_organiser_delete on public.event_instances is
  'Organisers may delete instances for events they own.';

create policy event_instances_admin_all
  on public.event_instances
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy event_instances_admin_all on public.event_instances is
  'Platform admins may manage every event instance.';

create policy ticket_types_public_published_select
  on public.ticket_types
  for select
  using (
    exists (
      select 1
      from public.events e
      where e.id = ticket_types.event_id
        and e.status = 'published'
    )
  );

comment on policy ticket_types_public_published_select on public.ticket_types is
  'Ticket types are public only when the parent event is published.';

create policy ticket_types_organiser_select
  on public.ticket_types
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = ticket_types.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_types_organiser_insert
  on public.ticket_types
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = ticket_types.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_types_organiser_update
  on public.ticket_types
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = ticket_types.event_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = ticket_types.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_types_organiser_delete
  on public.ticket_types
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = ticket_types.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy ticket_types_organiser_select on public.ticket_types is
  'Organisers may read ticket types for their events regardless of publish status.';
comment on policy ticket_types_organiser_insert on public.ticket_types is
  'Organisers may create ticket types for events they own.';
comment on policy ticket_types_organiser_update on public.ticket_types is
  'Organisers may update ticket types for events they own.';
comment on policy ticket_types_organiser_delete on public.ticket_types is
  'Organisers may delete ticket types for events they own.';

create policy ticket_types_admin_all
  on public.ticket_types
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy ticket_types_admin_all on public.ticket_types is
  'Platform admins may manage every ticket type.';

-- tickets: holder, event organiser, or admin may read (includes qr_secret/pin_hash); no client writes.
create policy tickets_holder_select
  on public.tickets
  for select
  to authenticated
  using (holder_user_id = (select auth.uid()));

comment on policy tickets_holder_select on public.tickets is
  'Ticket holders may read their own tickets including qr_secret and pin_hash.';

create policy tickets_organiser_select
  on public.tickets
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.event_instances ei
      join public.events e on e.id = ei.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where ei.id = tickets.instance_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy tickets_organiser_select on public.tickets is
  'Event organisers may read tickets for their events including secrets for check-in.';

create policy tickets_admin_all
  on public.tickets
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy tickets_admin_all on public.tickets is
  'Platform admins may manage every ticket row.';

-- API roles need table privileges; RLS policies enforce authorization.
grant select, insert, update, delete on table public.services to authenticated, service_role;
grant select, insert, update, delete on table public.jobs to authenticated, service_role;
grant select, insert, update, delete on table public.job_quotes to authenticated, service_role;
grant select, insert, update, delete on table public.events to authenticated, service_role;
grant select, insert, update, delete on table public.event_instances to authenticated, service_role;
grant select, insert, update, delete on table public.ticket_types to authenticated, service_role;
grant select, insert, update, delete on table public.tickets to authenticated, service_role;

grant select on table public.services to anon;
grant select on table public.events to anon;
grant select on table public.event_instances to anon;
grant select on table public.ticket_types to anon;
