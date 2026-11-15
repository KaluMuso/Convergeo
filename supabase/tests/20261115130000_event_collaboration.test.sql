-- pgTAP checks for 20261115130000_event_collaboration.sql (state machine, guards, RLS).
-- Failure paths: approve twice, non-organiser approves, publish before approval.

begin;

select plan(24);

create or replace function pg_temp.raises(p_sql text, p_state text)
returns boolean language plpgsql as $$
begin
  execute p_sql;
  return false;
exception when others then
  return sqlstate = p_state;
end;
$$;

insert into auth.users (id, email) values
  ('c0000000-0000-0000-0000-0000000000a1', 'prop@example.com'),
  ('c0000000-0000-0000-0000-0000000000a2', 'org@example.com'),
  ('c0000000-0000-0000-0000-0000000000a3', 'other@example.com')
on conflict (id) do nothing;
insert into public.profiles (id) values
  ('c0000000-0000-0000-0000-0000000000a1'),
  ('c0000000-0000-0000-0000-0000000000a2'),
  ('c0000000-0000-0000-0000-0000000000a3')
on conflict (id) do nothing;
insert into public.vendors (id, owner_user_id, slug, display_name, status) values
  ('d0000000-0000-0000-0000-0000000000b1', 'c0000000-0000-0000-0000-0000000000a1', 'cc-prop', 'Proposer', 'active'),
  ('d0000000-0000-0000-0000-0000000000b2', 'c0000000-0000-0000-0000-0000000000a2', 'cc-org', 'Organiser', 'active'),
  ('d0000000-0000-0000-0000-0000000000b3', 'c0000000-0000-0000-0000-0000000000a3', 'cc-other', 'Other', 'active');

insert into public.event_collab_requests (
  id, proposer_vendor_id, organiser_vendor_id, event_draft, checklist, revenue_share_bps
) values (
  'e0000000-0000-0000-0000-0000000000c1',
  'd0000000-0000-0000-0000-0000000000b1',
  'd0000000-0000-0000-0000-0000000000b2',
  '{"title":"Collab night","category":"music","city":"Lusaka"}',
  '{"venue":{"name":"Hall","landmark":"Near mall","lat":-15.4,"lng":28.3},
    "schedule":{"starts_at":"2031-01-01T18:00:00Z","ends_at":"2031-01-01T22:00:00Z"},
    "capacity":{"capacity":200},
    "tiers":[{"name":"General","price_ngwee":5000,"qty_cap":150},{"name":"Free","price_ngwee":0}]}',
  2500
);

select ok(
  pg_temp.raises(
    $q$update public.event_collab_requests set status = 'approved' where id = 'e0000000-0000-0000-0000-0000000000c1'$q$,
    '42501'),
  'raw status update is rejected');
select ok(
  pg_temp.raises(
    $q$insert into public.event_collab_requests (proposer_vendor_id, organiser_vendor_id, status)
       values ('d0000000-0000-0000-0000-0000000000b1','d0000000-0000-0000-0000-0000000000b2','approved')$q$,
    '42501'),
  'insert with a non-draft status is rejected');
select ok(
  pg_temp.raises(
    $q$insert into public.event_collab_requests (proposer_vendor_id, organiser_vendor_id)
       values ('d0000000-0000-0000-0000-0000000000b1','d0000000-0000-0000-0000-0000000000b1')$q$,
    '23514'),
  'proposer cannot also be the organiser');

-- publish before approval
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','publish',null,'collab-night')$q$,
    '55000'),
  'publish before submit/approval is rejected');

-- proposer submits; organiser-only actions refused for the proposer
select ok(
  (select status from public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a1','submit')) = 'submitted',
  'proposer submits');
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a1','approve')$q$,
    '42501'),
  'the proposer cannot approve');
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a3','approve')$q$,
    '42501'),
  'a third vendor cannot approve');
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','publish',null,'collab-night')$q$,
    '55000'),
  'publish while only submitted is rejected');
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','decline')$q$,
    '22023'),
  'decline needs a reason');
select ok(
  pg_temp.raises(
    $q$update public.event_collab_requests set revenue_share_bps = 9000 where id = 'e0000000-0000-0000-0000-0000000000c1'$q$,
    '55000'),
  'proposal is frozen once submitted');

-- changes requested -> resubmit
select ok(
  (select status from public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','request_changes','Please confirm the generator')) = 'changes_requested',
  'organiser asks for changes');
update public.event_collab_requests set revenue_share_bps = 2000
  where id = 'e0000000-0000-0000-0000-0000000000c1';
select ok(
  (select revenue_share_bps from public.event_collab_requests where id = 'e0000000-0000-0000-0000-0000000000c1') = 2000,
  'proposal editable while changes are requested');
select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a1','submit');

-- approve once, twice fails
select ok(
  (select status from public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','approve')) = 'approved',
  'organiser approves');
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','approve')$q$,
    '55000'),
  'approving twice is rejected');
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a1','publish',null,'collab-night')$q$,
    '42501'),
  'the proposer cannot publish');

-- publish creates the event under the organiser with the split recorded
select ok(
  (select status from public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','publish',null,'collab-night')) = 'published',
  'organiser publishes');
select ok(
  exists (
    select 1 from public.events e
    join public.event_collab_requests r on r.event_id = e.id
    where r.id = 'e0000000-0000-0000-0000-0000000000c1'
      and e.organiser_vendor_id = 'd0000000-0000-0000-0000-0000000000b2'
      and e.status = 'published' and e.slug = 'collab-night'),
  'event is published under the organiser');
select ok(
  (select co_host_vendor_id = 'd0000000-0000-0000-0000-0000000000b1' and co_host_share_bps = 2000
   from public.event_revenue_splits where collaboration_request_id = 'e0000000-0000-0000-0000-0000000000c1'),
  'co-host and share (bps) are recorded');
select ok(
  (select count(*) from public.ticket_types tt join public.event_collab_requests r on r.event_id = tt.event_id
   where r.id = 'e0000000-0000-0000-0000-0000000000c1') = 2,
  'ticket tiers are created');
select ok(
  pg_temp.raises(
    $q$select public.event_collab_transition('e0000000-0000-0000-0000-0000000000c1','c0000000-0000-0000-0000-0000000000a2','publish',null,'collab-night-2')$q$,
    '55000'),
  'publishing twice is rejected');

-- audit is complete and append-only
select ok(
  (select count(*) from public.event_collab_audit where request_id = 'e0000000-0000-0000-0000-0000000000c1') = 5,
  'every transition is audited');
select ok(
  pg_temp.raises(
    $q$delete from public.event_collab_audit where request_id = 'e0000000-0000-0000-0000-0000000000c1'$q$,
    '42501'),
  'audit rows cannot be deleted');

-- RLS: parties read, outsiders do not
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"c0000000-0000-0000-0000-0000000000a3","role":"authenticated"}', true);
select ok(
  (select count(*) from public.event_collab_requests) = 0
  and (select count(*) from public.event_collab_audit) = 0
  and (select count(*) from public.event_revenue_splits) = 0,
  'an unrelated vendor sees no requests, audit rows or splits');
select set_config('request.jwt.claims', '{"sub":"c0000000-0000-0000-0000-0000000000a1","role":"authenticated"}', true);
select ok(
  (select count(*) from public.event_collab_requests) = 1
  and (select count(*) from public.event_revenue_splits) = 1,
  'the proposing vendor reads its request and split');
reset role;

select * from finish();
rollback;
