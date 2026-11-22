-- Intercity reference rate cards (logistics phase 1, manual lane only).
--
-- Reference prices transcribed from operator price-list PHOTOS supplied by the
-- founder on 2026-11-13. They are NOT quotes and drive NO booking automation:
-- operations read them when arranging a depot-to-depot parcel by hand.
-- Every row says "price list photo, verify" and must be confirmed by phone or
-- at the depot before a customer is charged.
--
--   * Town Star Courier & Logistics Ltd, "Lusaka price list" (photos
--     ec50d0cd / 88ca65f0). Footnote on the list: compensation for loss or
--     damage ONLY up to the value declared by the customer -> always declare
--     the order value on the waybill. "Large" prices read "K.. & above".
--     Kasempa appears twice on the photo with identical prices (stored once).
--     "Kasumbalesa" is listed under North-Western on the photo; kept as shown.
--   * A second, unnamed operator's longer list (photo 38da873a, low
--     resolution): rows that could be read; carrier name unknown. Confidence
--     'low'. Units on that list are small/medium/large "plastic" (bag).
--
-- Amounts are integer ngwee (K35 = 3500). effective_from 2026-11-01.
--
-- Down (manual): drop table public.intercity_rate_cards;

create table if not exists public.intercity_rate_cards (
  id uuid primary key default gen_random_uuid(),
  carrier_name text not null check (char_length(btrim(carrier_name)) between 2 and 120),
  origin_town text not null default 'Lusaka',
  province text not null,
  destination_town text not null check (char_length(btrim(destination_town)) between 2 and 80),
  small_parcel_ngwee bigint check (small_parcel_ngwee is null or small_parcel_ngwee > 0),
  medium_parcel_ngwee bigint check (medium_parcel_ngwee is null or medium_parcel_ngwee > 0),
  large_parcel_ngwee bigint check (large_parcel_ngwee is null or large_parcel_ngwee > 0),
  large_is_minimum boolean not null default true,
  liability_note text,
  source text not null,
  confidence text not null default 'legible' check (confidence in ('legible', 'low', 'verified')),
  effective_from date not null default date '2026-11-01',
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create unique index if not exists intercity_rate_cards_carrier_route_key
  on public.intercity_rate_cards (lower(carrier_name), lower(origin_town), lower(destination_town), effective_from);
create index if not exists intercity_rate_cards_destination_idx
  on public.intercity_rate_cards (lower(destination_town)) where active;

drop trigger if exists intercity_rate_cards_set_updated_at on public.intercity_rate_cards;
create trigger intercity_rate_cards_set_updated_at
  before update on public.intercity_rate_cards
  for each row execute function public.set_updated_at();

alter table public.intercity_rate_cards enable row level security;
alter table public.intercity_rate_cards force row level security;
drop policy if exists intercity_rate_cards_admin_select on public.intercity_rate_cards;
create policy intercity_rate_cards_admin_select
  on public.intercity_rate_cards for select to authenticated
  using (public.has_role('admin'));
revoke all on table public.intercity_rate_cards from anon, authenticated;
grant select on table public.intercity_rate_cards to authenticated;
grant select, insert, update, delete on table public.intercity_rate_cards to service_role;

comment on table public.intercity_rate_cards is
  'Reference intercity parcel prices from operator price-list photos (verify before use). '
  'Manual lane only: no booking automation reads this table.';

insert into public.intercity_rate_cards (
  carrier_name, origin_town, province, destination_town,
  small_parcel_ngwee, medium_parcel_ngwee, large_parcel_ngwee, large_is_minimum,
  source, confidence
) values
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Central', 'Kapiri Mposhi', 3500, 4500, 6500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Central', 'Kabwe', 3500, 4500, 6500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Kafue', 2500, 3000, 5500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Chirundu', 2500, 3000, 5500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Mazabuka', 3500, 5500, 8500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Monze', 3500, 5500, 8500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Choma', 3500, 5500, 8500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Zimba', 3500, 5500, 8500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Livingstone', 3500, 5500, 8500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Southern', 'Kazungula', 3500, 5500, 8500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'North-Western', 'Solwezi', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'North-Western', 'Kasempa', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'North-Western', 'Kalumbila', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'North-Western', 'Kisasa', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'North-Western', 'Lumwana', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'North-Western', 'Kasumbalesa', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Muchinga', 'Mpika', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Muchinga', 'Nakonde', 8500, 11500, 13500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Copperbelt', 'Ndola', 3500, 4500, 6500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Copperbelt', 'Kitwe', 3500, 4500, 6500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Copperbelt', 'Luanshya', 3500, 4500, 6500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Copperbelt', 'Chingola', 3500, 4500, 6500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Town Star Courier & Logistics Ltd', 'Lusaka', 'Copperbelt', 'Chililabombwe', 3500, 4500, 6500, true, 'price list photo, verify (ec50d0cd / 88ca65f0)', 'legible'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Kitwe', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Ndola', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Kapiri Mposhi', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Kabwe', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Mufulira', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Luanshya', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Chingola', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Kalulushi', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Chililabombwe', 3000, 4000, 5000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Ibenga', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Mpongwe', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Copperbelt', 'Chambeshi', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Livingstone', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Monze', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Mazabuka', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Choma', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Kalomo', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Pemba', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Batoka', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Mazoka', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Zimba', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Kafue', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Southern', 'Kazungula', 10000, 15000, 20000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Western', 'Mongu', 7000, 10000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Western', 'Kaoma', 7000, 10000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Western', 'Senanga', 10000, 15000, 20000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Western', 'Sesheke', 10000, 15000, 20000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Western', 'Sioma', 10000, 15000, 20000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Western', 'Lukulu', 10000, 15000, 20000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Western', 'Kalabo', 10000, 15000, 20000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Solwezi', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Kalumbila', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Kisasa', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Manyama', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Lumwana', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Zambezi', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Chavuma', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Manyinga', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'North-Western', 'Kabompo', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Luapula', 'Mansa', 7000, 10000, 13000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Central', 'Mkushi', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Central', 'Serenje', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Luapula', 'Kashikishi', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Luapula', 'Mwense', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Luapula', 'Samfya', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Luapula', 'Mbereshi', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Luapula', 'Kazembe', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Chipata', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Nyimba', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Petauke', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Katete', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Sinda', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Lundazi', 8000, 10000, 13000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Lumezi', 8000, 10000, 13000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Mfuwe', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Chama', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Eastern', 'Mambwe', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Kasama', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Mpika', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Mununga', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Chilonga', 5000, 7000, 10000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Shiwang''andu', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Isoka', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Chinsali', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Kapasa Makasa', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low'),
  ('Unidentified operator (price list photo 38da873a)', 'Lusaka', 'Northern', 'Nakonde', 10000, 13000, 15000, true, 'price list photo, verify (38da873a, low resolution)', 'low')
on conflict do nothing;

update public.intercity_rate_cards
set liability_note = 'Town Star compensates loss or damage only up to the value declared by the '
                     'customer: declare the full order value on every waybill.'
where carrier_name = 'Town Star Courier & Logistics Ltd' and liability_note is null;
