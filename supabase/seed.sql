-- M03-P10: Catalog seed — category tree (8 departments) + canonical product stubs.
-- Idempotent: stable UUIDs + ON CONFLICT DO NOTHING. Founder-reviewable.
-- Applied via `supabase db reset` when [db.seed] enabled, or manually / in seed.test.sql.

begin;

-- ---------------------------------------------------------------------------
-- Category tree (8 departments → subcategories)
-- ---------------------------------------------------------------------------

-- Department: Groceries & Staples
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000001-0000-4000-8000-000000000001', null, 'Groceries & Staples', 'groceries-staples', 'groceries-staples', 'groceries', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000001-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Rice & Grains', 'rice-grains', 'groceries-staples/rice-grains', 'groceries', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000002-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Cooking Oil', 'cooking-oil', 'groceries-staples/cooking-oil', 'groceries', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000003-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Sugar & Sweeteners', 'sugar-sweeteners', 'groceries-staples/sugar-sweeteners', 'groceries', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000004-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Flour & Baking', 'flour-baking', 'groceries-staples/flour-baking', 'groceries', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000005-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Pasta & Noodles', 'pasta-noodles', 'groceries-staples/pasta-noodles', 'groceries', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000006-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Canned Goods', 'canned-goods', 'groceries-staples/canned-goods', 'groceries', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000007-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Spices & Seasonings', 'spices-seasonings', 'groceries-staples/spices-seasonings', 'groceries', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000008-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Tea & Coffee', 'tea-coffee', 'groceries-staples/tea-coffee', 'groceries', 7
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000009-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Snacks', 'snacks', 'groceries-staples/snacks', 'groceries', 8
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000010-0000-4000-8000-000000000001', 'c00000001-0000-4000-8000-000000000001', 'Beverages', 'beverages', 'groceries-staples/beverages', 'groceries', 9
) on conflict (id) do nothing;

-- Department: Personal Care & Beauty
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000002-0000-4000-8000-000000000001', null, 'Personal Care & Beauty', 'personal-care-beauty', 'personal-care-beauty', 'fashion_beauty', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000011-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Skincare', 'skincare', 'personal-care-beauty/skincare', 'fashion_beauty', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000012-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Hair Care', 'hair-care', 'personal-care-beauty/hair-care', 'fashion_beauty', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000013-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Body Care', 'body-care', 'personal-care-beauty/body-care', 'fashion_beauty', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000014-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Oral Care', 'oral-care', 'personal-care-beauty/oral-care', 'fashion_beauty', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000015-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Deodorants', 'deodorants', 'personal-care-beauty/deodorants', 'fashion_beauty', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000016-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Makeup', 'makeup', 'personal-care-beauty/makeup', 'fashion_beauty', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000017-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Men''s Grooming', 'mens-grooming', 'personal-care-beauty/mens-grooming', 'fashion_beauty', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000018-0000-4000-8000-000000000001', 'c00000002-0000-4000-8000-000000000001', 'Baby Care', 'baby-care', 'personal-care-beauty/baby-care', 'fashion_beauty', 7
) on conflict (id) do nothing;

-- Department: Fashion
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000003-0000-4000-8000-000000000001', null, 'Fashion', 'fashion', 'fashion', 'fashion_beauty', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000019-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Chitenge & Fabric', 'chitenge-fabric', 'fashion/chitenge-fabric', 'fashion_beauty', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000020-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Women''s Clothing', 'womens-clothing', 'fashion/womens-clothing', 'fashion_beauty', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000021-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Men''s Clothing', 'mens-clothing', 'fashion/mens-clothing', 'fashion_beauty', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000022-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Kids Clothing', 'kids-clothing', 'fashion/kids-clothing', 'fashion_beauty', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000023-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Footwear', 'footwear', 'fashion/footwear', 'fashion_beauty', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000024-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Bags & Accessories', 'bags-accessories', 'fashion/bags-accessories', 'fashion_beauty', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000025-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Jewelry', 'jewelry', 'fashion/jewelry', 'fashion_beauty', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000026-0000-4000-8000-000000000001', 'c00000003-0000-4000-8000-000000000001', 'Traditional Wear', 'traditional-wear', 'fashion/traditional-wear', 'fashion_beauty', 7
) on conflict (id) do nothing;

-- Department: Electronics
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000004-0000-4000-8000-000000000001', null, 'Electronics', 'electronics', 'electronics', 'electronics', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000027-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'Mobile Phones', 'mobile-phones', 'electronics/mobile-phones', 'electronics', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000028-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'Phone Accessories', 'phone-accessories', 'electronics/phone-accessories', 'electronics', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000029-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'Laptops & Computers', 'laptops-computers', 'electronics/laptops-computers', 'electronics', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000030-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'TVs & Audio', 'tvs-audio', 'electronics/tvs-audio', 'electronics', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000031-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'Solar & Power', 'solar-power', 'electronics/solar-power', 'electronics', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000032-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'Cameras', 'cameras', 'electronics/cameras', 'electronics', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000033-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'Gaming', 'gaming', 'electronics/gaming', 'electronics', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000034-0000-4000-8000-000000000001', 'c00000004-0000-4000-8000-000000000001', 'Small Appliances', 'small-appliances', 'electronics/small-appliances', 'electronics', 7
) on conflict (id) do nothing;

-- Department: Home & Living
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000005-0000-4000-8000-000000000001', null, 'Home & Living', 'home-living', 'home-living', 'home', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000035-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Furniture', 'furniture', 'home-living/furniture', 'home', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000036-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Bedding', 'bedding', 'home-living/bedding', 'home', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000037-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Kitchenware', 'kitchenware', 'home-living/kitchenware', 'home', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000038-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Home Decor', 'home-decor', 'home-living/home-decor', 'home', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000039-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Cleaning Supplies', 'cleaning-supplies', 'home-living/cleaning-supplies', 'home', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000040-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Storage', 'storage', 'home-living/storage', 'home', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000041-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Lighting', 'lighting', 'home-living/lighting', 'home', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000042-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Bathroom', 'bathroom', 'home-living/bathroom', 'home', 7
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000043-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Garden & Outdoor', 'garden-outdoor', 'home-living/garden-outdoor', 'home', 8
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000044-0000-4000-8000-000000000001', 'c00000005-0000-4000-8000-000000000001', 'Mattresses', 'mattresses', 'home-living/mattresses', 'home', 9
) on conflict (id) do nothing;

-- Department: Office & Stationery
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000006-0000-4000-8000-000000000001', null, 'Office & Stationery', 'office-stationery', 'office-stationery', 'supplies', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000045-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'Paper & Notebooks', 'paper-notebooks', 'office-stationery/paper-notebooks', 'supplies', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000046-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'Pens & Writing', 'pens-writing', 'office-stationery/pens-writing', 'supplies', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000047-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'Office Furniture', 'office-furniture', 'office-stationery/office-furniture', 'supplies', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000048-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'Printers & Ink', 'printers-ink', 'office-stationery/printers-ink', 'supplies', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000049-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'Filing & Storage', 'filing-storage', 'office-stationery/filing-storage', 'supplies', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000050-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'School Supplies', 'school-supplies', 'office-stationery/school-supplies', 'supplies', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000051-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'Calculators', 'calculators', 'office-stationery/calculators', 'supplies', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000052-0000-4000-8000-000000000001', 'c00000006-0000-4000-8000-000000000001', 'Art Supplies', 'art-supplies', 'office-stationery/art-supplies', 'supplies', 7
) on conflict (id) do nothing;

-- Department: Light Hardware
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000007-0000-4000-8000-000000000001', null, 'Light Hardware', 'light-hardware', 'light-hardware', 'home', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000053-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Hand Tools', 'hand-tools', 'light-hardware/hand-tools', 'home', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000054-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Electrical Supplies', 'electrical-supplies', 'light-hardware/electrical-supplies', 'home', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000055-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Plumbing', 'plumbing', 'light-hardware/plumbing', 'home', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000056-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Paint', 'paint', 'light-hardware/paint', 'home', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000057-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Locks & Security', 'locks-security', 'light-hardware/locks-security', 'home', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000058-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Fasteners', 'fasteners', 'light-hardware/fasteners', 'home', 5
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000059-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Garden Tools', 'garden-tools', 'light-hardware/garden-tools', 'home', 6
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000060-0000-4000-8000-000000000001', 'c00000007-0000-4000-8000-000000000001', 'Safety Equipment', 'safety-equipment', 'light-hardware/safety-equipment', 'home', 7
) on conflict (id) do nothing;

-- Department: Event Tickets
insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'c00000008-0000-4000-8000-000000000001', null, 'Event Tickets', 'event-tickets', 'event-tickets', 'event_tickets', 7
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000061-0000-4000-8000-000000000001', 'c00000008-0000-4000-8000-000000000001', 'Workshops & Education', 'workshops-education', 'event-tickets/workshops-education', 'event_tickets', 0
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000062-0000-4000-8000-000000000001', 'c00000008-0000-4000-8000-000000000001', 'Comedy & Theatre', 'comedy-theatre', 'event-tickets/comedy-theatre', 'event_tickets', 1
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000063-0000-4000-8000-000000000001', 'c00000008-0000-4000-8000-000000000001', 'Music & Nightlife', 'music-nightlife', 'event-tickets/music-nightlife', 'event_tickets', 2
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000064-0000-4000-8000-000000000001', 'c00000008-0000-4000-8000-000000000001', 'Community & Lifestyle', 'community-lifestyle', 'event-tickets/community-lifestyle', 'event_tickets', 3
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000065-0000-4000-8000-000000000001', 'c00000008-0000-4000-8000-000000000001', 'Cultural & Arts', 'cultural-arts', 'event-tickets/cultural-arts', 'event_tickets', 4
) on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values (
  'd00000066-0000-4000-8000-000000000001', 'c00000008-0000-4000-8000-000000000001', 'Free RSVP Events', 'free-rsvp', 'event-tickets/free-rsvp', 'event_tickets', 5
) on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Canonical product stubs (~150)
-- ---------------------------------------------------------------------------

-- Products: Groceries & Staples
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000001-0000-4000-8000-000000000001', 'Rice & Grains Standard', 'rice-grains-standard', null, '{"unit": "each"}'::jsonb,
  'd00000001-0000-4000-8000-000000000001', '{"umucele","mpunga","rice & grains"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000002-0000-4000-8000-000000000001', 'Rice & Grains Premium', 'rice-grains-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000001-0000-4000-8000-000000000001', '{"umucele","mpunga","rice & grains"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000003-0000-4000-8000-000000000001', 'Cooking Oil Standard', 'cooking-oil-standard', null, '{"unit": "each"}'::jsonb,
  'd00000002-0000-4000-8000-000000000001', '{"mafuta","mafuta a kupika","cooking oil"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000004-0000-4000-8000-000000000001', 'Cooking Oil Premium', 'cooking-oil-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000002-0000-4000-8000-000000000001', '{"mafuta","mafuta a kupika","cooking oil"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000005-0000-4000-8000-000000000001', 'Sugar & Sweeteners Standard', 'sugar-sweeteners-standard', null, '{"unit": "each"}'::jsonb,
  'd00000003-0000-4000-8000-000000000001', '{"shuga","sukali","sugar & sweeteners"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000006-0000-4000-8000-000000000001', 'Sugar & Sweeteners Premium', 'sugar-sweeteners-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000003-0000-4000-8000-000000000001', '{"shuga","sukali","sugar & sweeteners"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000007-0000-4000-8000-000000000001', 'Flour & Baking Standard', 'flour-baking-standard', null, '{"unit": "each"}'::jsonb,
  'd00000004-0000-4000-8000-000000000001', '{"unga","flour","flour & baking"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000008-0000-4000-8000-000000000001', 'Flour & Baking Premium', 'flour-baking-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000004-0000-4000-8000-000000000001', '{"unga","flour","flour & baking"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000009-0000-4000-8000-000000000001', 'Pasta & Noodles Standard', 'pasta-noodles-standard', null, '{"unit": "each"}'::jsonb,
  'd00000005-0000-4000-8000-000000000001', '{"noodles","spaghetti","pasta & noodles"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000010-0000-4000-8000-000000000001', 'Pasta & Noodles Premium', 'pasta-noodles-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000005-0000-4000-8000-000000000001', '{"noodles","spaghetti","pasta & noodles"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000011-0000-4000-8000-000000000001', 'Canned Goods Standard', 'canned-goods-standard', null, '{"unit": "each"}'::jsonb,
  'd00000006-0000-4000-8000-000000000001', '{"canned","maboti","canned goods"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000012-0000-4000-8000-000000000001', 'Canned Goods Premium', 'canned-goods-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000006-0000-4000-8000-000000000001', '{"canned","maboti","canned goods"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000013-0000-4000-8000-000000000001', 'Spices & Seasonings Standard', 'spices-seasonings-standard', null, '{"unit": "each"}'::jsonb,
  'd00000007-0000-4000-8000-000000000001', '{"spices","ifishibisho","spices & seasonings"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000014-0000-4000-8000-000000000001', 'Spices & Seasonings Premium', 'spices-seasonings-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000007-0000-4000-8000-000000000001', '{"spices","ifishibisho","spices & seasonings"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000015-0000-4000-8000-000000000001', 'Tea & Coffee Standard', 'tea-coffee-standard', null, '{"unit": "each"}'::jsonb,
  'd00000008-0000-4000-8000-000000000001', '{"tii","kofi","tea & coffee"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000016-0000-4000-8000-000000000001', 'Tea & Coffee Premium', 'tea-coffee-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000008-0000-4000-8000-000000000001', '{"tii","kofi","tea & coffee"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000017-0000-4000-8000-000000000001', 'Snacks Standard', 'snacks-standard', null, '{"unit": "each"}'::jsonb,
  'd00000009-0000-4000-8000-000000000001', '{"snacks","ifilyashi"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000018-0000-4000-8000-000000000001', 'Snacks Premium', 'snacks-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000009-0000-4000-8000-000000000001', '{"snacks","ifilyashi"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000019-0000-4000-8000-000000000001', 'Beverages Standard', 'beverages-standard', null, '{"unit": "each"}'::jsonb,
  'd00000010-0000-4000-8000-000000000001', '{"drinks","zibanwi","beverages"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000020-0000-4000-8000-000000000001', 'Beverages Premium', 'beverages-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000010-0000-4000-8000-000000000001', '{"drinks","zibanwi","beverages"}', 'active'
) on conflict (id) do nothing;

-- Products: Personal Care & Beauty
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000021-0000-4000-8000-000000000001', 'Skincare Standard', 'skincare-standard', null, '{"unit": "each"}'::jsonb,
  'd00000011-0000-4000-8000-000000000001', '{"skin care","ubulungu bwa panshi","skincare"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000022-0000-4000-8000-000000000001', 'Skincare Premium', 'skincare-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000011-0000-4000-8000-000000000001', '{"skin care","ubulungu bwa panshi","skincare"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000023-0000-4000-8000-000000000001', 'Hair Care Standard', 'hair-care-standard', null, '{"unit": "each"}'::jsonb,
  'd00000012-0000-4000-8000-000000000001', '{"shampoo","ubulungu bwa mushishi","hair care"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000024-0000-4000-8000-000000000001', 'Hair Care Premium', 'hair-care-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000012-0000-4000-8000-000000000001', '{"shampoo","ubulungu bwa mushishi","hair care"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000025-0000-4000-8000-000000000001', 'Body Care Standard', 'body-care-standard', null, '{"unit": "each"}'::jsonb,
  'd00000013-0000-4000-8000-000000000001', '{"lotion","soap","body care"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000026-0000-4000-8000-000000000001', 'Body Care Premium', 'body-care-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000013-0000-4000-8000-000000000001', '{"lotion","soap","body care"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000027-0000-4000-8000-000000000001', 'Oral Care Standard', 'oral-care-standard', null, '{"unit": "each"}'::jsonb,
  'd00000014-0000-4000-8000-000000000001', '{"toothpaste","mano","oral care"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000028-0000-4000-8000-000000000001', 'Oral Care Premium', 'oral-care-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000014-0000-4000-8000-000000000001', '{"toothpaste","mano","oral care"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000029-0000-4000-8000-000000000001', 'Deodorants Standard', 'deodorants-standard', null, '{"unit": "each"}'::jsonb,
  'd00000015-0000-4000-8000-000000000001', '{"deo","perfume","deodorants"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000030-0000-4000-8000-000000000001', 'Deodorants Premium', 'deodorants-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000015-0000-4000-8000-000000000001', '{"deo","perfume","deodorants"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000031-0000-4000-8000-000000000001', 'Makeup Standard', 'makeup-standard', null, '{"unit": "each"}'::jsonb,
  'd00000016-0000-4000-8000-000000000001', '{"cosmetics","make up","makeup"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000032-0000-4000-8000-000000000001', 'Makeup Premium', 'makeup-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000016-0000-4000-8000-000000000001', '{"cosmetics","make up","makeup"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000033-0000-4000-8000-000000000001', 'Men''s Grooming Standard', 'mens-grooming-standard', null, '{"unit": "each"}'::jsonb,
  'd00000017-0000-4000-8000-000000000001', '{"shaving","kubelenga","men's grooming"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000034-0000-4000-8000-000000000001', 'Men''s Grooming Premium', 'mens-grooming-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000017-0000-4000-8000-000000000001', '{"shaving","kubelenga","men's grooming"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000035-0000-4000-8000-000000000001', 'Baby Care Standard', 'baby-care-standard', null, '{"unit": "each"}'::jsonb,
  'd00000018-0000-4000-8000-000000000001', '{"diapers","napkins","baby care"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000036-0000-4000-8000-000000000001', 'Baby Care Premium', 'baby-care-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000018-0000-4000-8000-000000000001', '{"diapers","napkins","baby care"}', 'active'
) on conflict (id) do nothing;

-- Products: Fashion
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000037-0000-4000-8000-000000000001', 'Chitenge & Fabric Standard', 'chitenge-fabric-standard', null, '{"unit": "each"}'::jsonb,
  'd00000019-0000-4000-8000-000000000001', '{"chitenge","chitange","fabric","chitenge & fabric"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000038-0000-4000-8000-000000000001', 'Chitenge & Fabric Premium', 'chitenge-fabric-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000019-0000-4000-8000-000000000001', '{"chitenge","chitange","fabric","chitenge & fabric"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000039-0000-4000-8000-000000000001', 'Women''s Clothing Standard', 'womens-clothing-standard', null, '{"unit": "each"}'::jsonb,
  'd00000020-0000-4000-8000-000000000001', '{"dress","nguwafwila","women's clothing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000040-0000-4000-8000-000000000001', 'Women''s Clothing Premium', 'womens-clothing-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000020-0000-4000-8000-000000000001', '{"dress","nguwafwila","women's clothing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000041-0000-4000-8000-000000000001', 'Men''s Clothing Standard', 'mens-clothing-standard', null, '{"unit": "each"}'::jsonb,
  'd00000021-0000-4000-8000-000000000001', '{"shirt","trousers","men's clothing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000042-0000-4000-8000-000000000001', 'Men''s Clothing Premium', 'mens-clothing-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000021-0000-4000-8000-000000000001', '{"shirt","trousers","men's clothing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000043-0000-4000-8000-000000000001', 'Kids Clothing Standard', 'kids-clothing-standard', null, '{"unit": "each"}'::jsonb,
  'd00000022-0000-4000-8000-000000000001', '{"children","bana","kids clothing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000044-0000-4000-8000-000000000001', 'Kids Clothing Premium', 'kids-clothing-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000022-0000-4000-8000-000000000001', '{"children","bana","kids clothing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000045-0000-4000-8000-000000000001', 'Footwear Standard', 'footwear-standard', null, '{"unit": "each"}'::jsonb,
  'd00000023-0000-4000-8000-000000000001', '{"shoes","sapato","footwear"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000046-0000-4000-8000-000000000001', 'Footwear Premium', 'footwear-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000023-0000-4000-8000-000000000001', '{"shoes","sapato","footwear"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000047-0000-4000-8000-000000000001', 'Bags & Accessories Standard', 'bags-accessories-standard', null, '{"unit": "each"}'::jsonb,
  'd00000024-0000-4000-8000-000000000001', '{"handbag","bag","bags & accessories"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000048-0000-4000-8000-000000000001', 'Bags & Accessories Premium', 'bags-accessories-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000024-0000-4000-8000-000000000001', '{"handbag","bag","bags & accessories"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000049-0000-4000-8000-000000000001', 'Jewelry Standard', 'jewelry-standard', null, '{"unit": "each"}'::jsonb,
  'd00000025-0000-4000-8000-000000000001', '{"necklace","ngozi","jewelry"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000050-0000-4000-8000-000000000001', 'Jewelry Premium', 'jewelry-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000025-0000-4000-8000-000000000001', '{"necklace","ngozi","jewelry"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000051-0000-4000-8000-000000000001', 'Traditional Wear Standard', 'traditional-wear-standard', null, '{"unit": "each"}'::jsonb,
  'd00000026-0000-4000-8000-000000000001', '{"traditional","ifipe","traditional wear"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000052-0000-4000-8000-000000000001', 'Traditional Wear Premium', 'traditional-wear-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000026-0000-4000-8000-000000000001', '{"traditional","ifipe","traditional wear"}', 'active'
) on conflict (id) do nothing;

-- Products: Electronics
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000053-0000-4000-8000-000000000001', 'Mobile Phones Standard', 'mobile-phones-standard', null, '{"unit": "each"}'::jsonb,
  'd00000027-0000-4000-8000-000000000001', '{"phone","foni","phone ya m'manja","mobile phones"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000054-0000-4000-8000-000000000001', 'Mobile Phones Premium', 'mobile-phones-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000027-0000-4000-8000-000000000001', '{"phone","foni","phone ya m'manja","mobile phones"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000055-0000-4000-8000-000000000001', 'Phone Accessories Standard', 'phone-accessories-standard', null, '{"unit": "each"}'::jsonb,
  'd00000028-0000-4000-8000-000000000001', '{"charger","case","phone accessories"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000056-0000-4000-8000-000000000001', 'Phone Accessories Premium', 'phone-accessories-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000028-0000-4000-8000-000000000001', '{"charger","case","phone accessories"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000057-0000-4000-8000-000000000001', 'Laptops & Computers Standard', 'laptops-computers-standard', null, '{"unit": "each"}'::jsonb,
  'd00000029-0000-4000-8000-000000000001', '{"laptop","computer","laptops & computers"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000058-0000-4000-8000-000000000001', 'Laptops & Computers Premium', 'laptops-computers-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000029-0000-4000-8000-000000000001', '{"laptop","computer","laptops & computers"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000059-0000-4000-8000-000000000001', 'TVs & Audio Standard', 'tvs-audio-standard', null, '{"unit": "each"}'::jsonb,
  'd00000030-0000-4000-8000-000000000001', '{"tv","speaker","tvs & audio"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000060-0000-4000-8000-000000000001', 'TVs & Audio Premium', 'tvs-audio-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000030-0000-4000-8000-000000000001', '{"tv","speaker","tvs & audio"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000061-0000-4000-8000-000000000001', 'Solar & Power Standard', 'solar-power-standard', null, '{"unit": "each"}'::jsonb,
  'd00000031-0000-4000-8000-000000000001', '{"solar","battery","panji","solar & power"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000062-0000-4000-8000-000000000001', 'Solar & Power Premium', 'solar-power-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000031-0000-4000-8000-000000000001', '{"solar","battery","panji","solar & power"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000063-0000-4000-8000-000000000001', 'Cameras Standard', 'cameras-standard', null, '{"unit": "each"}'::jsonb,
  'd00000032-0000-4000-8000-000000000001', '{"camera","kamera","cameras"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000064-0000-4000-8000-000000000001', 'Cameras Premium', 'cameras-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000032-0000-4000-8000-000000000001', '{"camera","kamera","cameras"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000065-0000-4000-8000-000000000001', 'Gaming Standard', 'gaming-standard', null, '{"unit": "each"}'::jsonb,
  'd00000033-0000-4000-8000-000000000001', '{"console","game","gaming"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000066-0000-4000-8000-000000000001', 'Gaming Premium', 'gaming-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000033-0000-4000-8000-000000000001', '{"console","game","gaming"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000067-0000-4000-8000-000000000001', 'Small Appliances Standard', 'small-appliances-standard', null, '{"unit": "each"}'::jsonb,
  'd00000034-0000-4000-8000-000000000001', '{"kettle","blender","small appliances"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000068-0000-4000-8000-000000000001', 'Small Appliances Premium', 'small-appliances-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000034-0000-4000-8000-000000000001', '{"kettle","blender","small appliances"}', 'active'
) on conflict (id) do nothing;

-- Products: Home & Living
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000069-0000-4000-8000-000000000001', 'Furniture Standard', 'furniture-standard', null, '{"unit": "each"}'::jsonb,
  'd00000035-0000-4000-8000-000000000001', '{"table","chair","furniture"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000070-0000-4000-8000-000000000001', 'Furniture Premium', 'furniture-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000035-0000-4000-8000-000000000001', '{"table","chair","furniture"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000071-0000-4000-8000-000000000001', 'Bedding Standard', 'bedding-standard', null, '{"unit": "each"}'::jsonb,
  'd00000036-0000-4000-8000-000000000001', '{"bedsheet","pillow","blanket","bedding"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000072-0000-4000-8000-000000000001', 'Bedding Premium', 'bedding-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000036-0000-4000-8000-000000000001', '{"bedsheet","pillow","blanket","bedding"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000073-0000-4000-8000-000000000001', 'Kitchenware Standard', 'kitchenware-standard', null, '{"unit": "each"}'::jsonb,
  'd00000037-0000-4000-8000-000000000001', '{"pots","pans","ndiro","kitchenware"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000074-0000-4000-8000-000000000001', 'Kitchenware Premium', 'kitchenware-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000037-0000-4000-8000-000000000001', '{"pots","pans","ndiro","kitchenware"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000075-0000-4000-8000-000000000001', 'Home Decor Standard', 'home-decor-standard', null, '{"unit": "each"}'::jsonb,
  'd00000038-0000-4000-8000-000000000001', '{"curtains","decor","home decor"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000076-0000-4000-8000-000000000001', 'Home Decor Premium', 'home-decor-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000038-0000-4000-8000-000000000001', '{"curtains","decor","home decor"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000077-0000-4000-8000-000000000001', 'Cleaning Supplies Standard', 'cleaning-supplies-standard', null, '{"unit": "each"}'::jsonb,
  'd00000039-0000-4000-8000-000000000001', '{"detergent","broom","cleaning supplies"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000078-0000-4000-8000-000000000001', 'Cleaning Supplies Premium', 'cleaning-supplies-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000039-0000-4000-8000-000000000001', '{"detergent","broom","cleaning supplies"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000079-0000-4000-8000-000000000001', 'Storage Standard', 'storage-standard', null, '{"unit": "each"}'::jsonb,
  'd00000040-0000-4000-8000-000000000001', '{"boxes","containers","storage"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000080-0000-4000-8000-000000000001', 'Storage Premium', 'storage-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000040-0000-4000-8000-000000000001', '{"boxes","containers","storage"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000081-0000-4000-8000-000000000001', 'Lighting Standard', 'lighting-standard', null, '{"unit": "each"}'::jsonb,
  'd00000041-0000-4000-8000-000000000001', '{"bulb","lamp","kuwala","lighting"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000082-0000-4000-8000-000000000001', 'Lighting Premium', 'lighting-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000041-0000-4000-8000-000000000001', '{"bulb","lamp","kuwala","lighting"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000083-0000-4000-8000-000000000001', 'Bathroom Standard', 'bathroom-standard', null, '{"unit": "each"}'::jsonb,
  'd00000042-0000-4000-8000-000000000001', '{"towel","bathroom"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000084-0000-4000-8000-000000000001', 'Bathroom Premium', 'bathroom-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000042-0000-4000-8000-000000000001', '{"towel","bathroom"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000085-0000-4000-8000-000000000001', 'Garden & Outdoor Standard', 'garden-outdoor-standard', null, '{"unit": "each"}'::jsonb,
  'd00000043-0000-4000-8000-000000000001', '{"garden","outdoor","garden & outdoor"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000086-0000-4000-8000-000000000001', 'Garden & Outdoor Premium', 'garden-outdoor-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000043-0000-4000-8000-000000000001', '{"garden","outdoor","garden & outdoor"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000087-0000-4000-8000-000000000001', 'Mattresses Standard', 'mattresses-standard', null, '{"unit": "each"}'::jsonb,
  'd00000044-0000-4000-8000-000000000001', '{"mattress","bed","mattresses"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000088-0000-4000-8000-000000000001', 'Mattresses Premium', 'mattresses-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000044-0000-4000-8000-000000000001', '{"mattress","bed","mattresses"}', 'active'
) on conflict (id) do nothing;

-- Products: Office & Stationery
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000089-0000-4000-8000-000000000001', 'Paper & Notebooks Standard', 'paper-notebooks-standard', null, '{"unit": "each"}'::jsonb,
  'd00000045-0000-4000-8000-000000000001', '{"notebook","paper","paper & notebooks"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000090-0000-4000-8000-000000000001', 'Paper & Notebooks Premium', 'paper-notebooks-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000045-0000-4000-8000-000000000001', '{"notebook","paper","paper & notebooks"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000091-0000-4000-8000-000000000001', 'Pens & Writing Standard', 'pens-writing-standard', null, '{"unit": "each"}'::jsonb,
  'd00000046-0000-4000-8000-000000000001', '{"pen","pencil","pens & writing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000092-0000-4000-8000-000000000001', 'Pens & Writing Premium', 'pens-writing-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000046-0000-4000-8000-000000000001', '{"pen","pencil","pens & writing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000093-0000-4000-8000-000000000001', 'Office Furniture Standard', 'office-furniture-standard', null, '{"unit": "each"}'::jsonb,
  'd00000047-0000-4000-8000-000000000001', '{"desk","office chair","office furniture"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000094-0000-4000-8000-000000000001', 'Office Furniture Premium', 'office-furniture-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000047-0000-4000-8000-000000000001', '{"desk","office chair","office furniture"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000095-0000-4000-8000-000000000001', 'Printers & Ink Standard', 'printers-ink-standard', null, '{"unit": "each"}'::jsonb,
  'd00000048-0000-4000-8000-000000000001', '{"printer","ink","printers & ink"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000096-0000-4000-8000-000000000001', 'Printers & Ink Premium', 'printers-ink-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000048-0000-4000-8000-000000000001', '{"printer","ink","printers & ink"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000097-0000-4000-8000-000000000001', 'Filing & Storage Standard', 'filing-storage-standard', null, '{"unit": "each"}'::jsonb,
  'd00000049-0000-4000-8000-000000000001', '{"files","folders","filing & storage"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000098-0000-4000-8000-000000000001', 'Filing & Storage Premium', 'filing-storage-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000049-0000-4000-8000-000000000001', '{"files","folders","filing & storage"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000099-0000-4000-8000-000000000001', 'School Supplies Standard', 'school-supplies-standard', null, '{"unit": "each"}'::jsonb,
  'd00000050-0000-4000-8000-000000000001', '{"school","cikolo","school supplies"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000100-0000-4000-8000-000000000001', 'School Supplies Premium', 'school-supplies-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000050-0000-4000-8000-000000000001', '{"school","cikolo","school supplies"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000101-0000-4000-8000-000000000001', 'Calculators Standard', 'calculators-standard', null, '{"unit": "each"}'::jsonb,
  'd00000051-0000-4000-8000-000000000001', '{"calculator","calculators"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000102-0000-4000-8000-000000000001', 'Calculators Premium', 'calculators-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000051-0000-4000-8000-000000000001', '{"calculator","calculators"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000103-0000-4000-8000-000000000001', 'Art Supplies Standard', 'art-supplies-standard', null, '{"unit": "each"}'::jsonb,
  'd00000052-0000-4000-8000-000000000001', '{"paint","brushes","art supplies"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000104-0000-4000-8000-000000000001', 'Art Supplies Premium', 'art-supplies-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000052-0000-4000-8000-000000000001', '{"paint","brushes","art supplies"}', 'active'
) on conflict (id) do nothing;

-- Products: Light Hardware
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000105-0000-4000-8000-000000000001', 'Hand Tools Standard', 'hand-tools-standard', null, '{"unit": "each"}'::jsonb,
  'd00000053-0000-4000-8000-000000000001', '{"hammer","spanner","hand tools"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000106-0000-4000-8000-000000000001', 'Hand Tools Premium', 'hand-tools-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000053-0000-4000-8000-000000000001', '{"hammer","spanner","hand tools"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000107-0000-4000-8000-000000000001', 'Electrical Supplies Standard', 'electrical-supplies-standard', null, '{"unit": "each"}'::jsonb,
  'd00000054-0000-4000-8000-000000000001', '{"wire","socket","electrical supplies"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000108-0000-4000-8000-000000000001', 'Electrical Supplies Premium', 'electrical-supplies-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000054-0000-4000-8000-000000000001', '{"wire","socket","electrical supplies"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000109-0000-4000-8000-000000000001', 'Plumbing Standard', 'plumbing-standard', null, '{"unit": "each"}'::jsonb,
  'd00000055-0000-4000-8000-000000000001', '{"pipes","tap","plumbing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000110-0000-4000-8000-000000000001', 'Plumbing Premium', 'plumbing-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000055-0000-4000-8000-000000000001', '{"pipes","tap","plumbing"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000111-0000-4000-8000-000000000001', 'Paint Standard', 'paint-standard', null, '{"unit": "each"}'::jsonb,
  'd00000056-0000-4000-8000-000000000001', '{"paint","varnish"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000112-0000-4000-8000-000000000001', 'Paint Premium', 'paint-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000056-0000-4000-8000-000000000001', '{"paint","varnish"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000113-0000-4000-8000-000000000001', 'Locks & Security Standard', 'locks-security-standard', null, '{"unit": "each"}'::jsonb,
  'd00000057-0000-4000-8000-000000000001', '{"lock","padlock","locks & security"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000114-0000-4000-8000-000000000001', 'Locks & Security Premium', 'locks-security-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000057-0000-4000-8000-000000000001', '{"lock","padlock","locks & security"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000115-0000-4000-8000-000000000001', 'Fasteners Standard', 'fasteners-standard', null, '{"unit": "each"}'::jsonb,
  'd00000058-0000-4000-8000-000000000001', '{"nails","screws","fasteners"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000116-0000-4000-8000-000000000001', 'Fasteners Premium', 'fasteners-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000058-0000-4000-8000-000000000001', '{"nails","screws","fasteners"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000117-0000-4000-8000-000000000001', 'Garden Tools Standard', 'garden-tools-standard', null, '{"unit": "each"}'::jsonb,
  'd00000059-0000-4000-8000-000000000001', '{"hoe","rake","garden tools"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000118-0000-4000-8000-000000000001', 'Garden Tools Premium', 'garden-tools-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000059-0000-4000-8000-000000000001', '{"hoe","rake","garden tools"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000119-0000-4000-8000-000000000001', 'Safety Equipment Standard', 'safety-equipment-standard', null, '{"unit": "each"}'::jsonb,
  'd00000060-0000-4000-8000-000000000001', '{"gloves","helmet","safety equipment"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000120-0000-4000-8000-000000000001', 'Safety Equipment Premium', 'safety-equipment-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000060-0000-4000-8000-000000000001', '{"gloves","helmet","safety equipment"}', 'active'
) on conflict (id) do nothing;

-- Products: Event Tickets
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000121-0000-4000-8000-000000000001', 'Workshops & Education Standard', 'workshops-education-standard', null, '{"unit": "each"}'::jsonb,
  'd00000061-0000-4000-8000-000000000001', '{"workshop","class","workshops & education"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000122-0000-4000-8000-000000000001', 'Workshops & Education Premium', 'workshops-education-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000061-0000-4000-8000-000000000001', '{"workshop","class","workshops & education"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000123-0000-4000-8000-000000000001', 'Comedy & Theatre Standard', 'comedy-theatre-standard', null, '{"unit": "each"}'::jsonb,
  'd00000062-0000-4000-8000-000000000001', '{"comedy","theatre","comedy & theatre"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000124-0000-4000-8000-000000000001', 'Comedy & Theatre Premium', 'comedy-theatre-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000062-0000-4000-8000-000000000001', '{"comedy","theatre","comedy & theatre"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000125-0000-4000-8000-000000000001', 'Music & Nightlife Standard', 'music-nightlife-standard', null, '{"unit": "each"}'::jsonb,
  'd00000063-0000-4000-8000-000000000001', '{"concert","music","music & nightlife"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000126-0000-4000-8000-000000000001', 'Music & Nightlife Premium', 'music-nightlife-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000063-0000-4000-8000-000000000001', '{"concert","music","music & nightlife"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000127-0000-4000-8000-000000000001', 'Community & Lifestyle Standard', 'community-lifestyle-standard', null, '{"unit": "each"}'::jsonb,
  'd00000064-0000-4000-8000-000000000001', '{"community","meetup","community & lifestyle"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000128-0000-4000-8000-000000000001', 'Community & Lifestyle Premium', 'community-lifestyle-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000064-0000-4000-8000-000000000001', '{"community","meetup","community & lifestyle"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000129-0000-4000-8000-000000000001', 'Cultural & Arts Standard', 'cultural-arts-standard', null, '{"unit": "each"}'::jsonb,
  'd00000065-0000-4000-8000-000000000001', '{"cultural","arts","cultural & arts"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000130-0000-4000-8000-000000000001', 'Cultural & Arts Premium', 'cultural-arts-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000065-0000-4000-8000-000000000001', '{"cultural","arts","cultural & arts"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000131-0000-4000-8000-000000000001', 'Free RSVP Events Standard', 'free-rsvp-standard', null, '{"unit": "each"}'::jsonb,
  'd00000066-0000-4000-8000-000000000001', '{"free event","rsvp","free rsvp events"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000132-0000-4000-8000-000000000001', 'Free RSVP Events Premium', 'free-rsvp-premium', null, '{"unit": "each","grade": "premium"}'::jsonb,
  'd00000066-0000-4000-8000-000000000001', '{"free event","rsvp","free rsvp events"}', 'active'
) on conflict (id) do nothing;

-- Featured canonical stubs (Zambia-relevant names)
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000133-0000-4000-8000-000000000001', 'Itel A70 Smartphone', 'itel-a70', 'Itel', '{"storage_gb": "128","ram_gb": "4"}'::jsonb,
  'd00000027-0000-4000-8000-000000000001', '{"foni","phone"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000134-0000-4000-8000-000000000001', 'Tecno Spark 20', 'tecno-spark-20', 'Tecno', '{"storage_gb": "128"}'::jsonb,
  'd00000027-0000-4000-8000-000000000001', '{"foni"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000135-0000-4000-8000-000000000001', 'Samsung Galaxy A15', 'samsung-a15', 'Samsung', '{"storage_gb": "128"}'::jsonb,
  'd00000027-0000-4000-8000-000000000001', '{"foni"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000136-0000-4000-8000-000000000001', '6-Yard Chitenge Print', 'chitenge-6yard', null, '{"length_yards": "6"}'::jsonb,
  'd00000019-0000-4000-8000-000000000001', '{"chitenge","chitange"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000137-0000-4000-8000-000000000001', 'Ankara Wax Fabric', 'ankara-wax', null, '{"length_yards": "6"}'::jsonb,
  'd00000019-0000-4000-8000-000000000001', '{"chitenge"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000138-0000-4000-8000-000000000001', '25kg Breakfast Mealie Meal', 'mealie-meal-25kg', 'Breakfast', '{"weight_kg": "25"}'::jsonb,
  'd00000004-0000-4000-8000-000000000001', '{"unga","mealie meal"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000139-0000-4000-8000-000000000001', '5L Cooking Oil', 'cooking-oil-5l', null, '{"volume_l": "5"}'::jsonb,
  'd00000002-0000-4000-8000-000000000001', '{"mafuta"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000140-0000-4000-8000-000000000001', '2kg Jasmine Rice', 'jasmine-rice-2kg', null, '{"weight_kg": "2"}'::jsonb,
  'd00000001-0000-4000-8000-000000000001', '{"mpunga","umucele"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000141-0000-4000-8000-000000000001', '100W Solar Panel Kit', 'solar-100w', null, '{"watts": "100"}'::jsonb,
  'd00000031-0000-4000-8000-000000000001', '{"panji","solar"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000142-0000-4000-8000-000000000001', '32 Inch Smart TV', 'tv-32-smart', null, '{"size_inches": "32"}'::jsonb,
  'd00000030-0000-4000-8000-000000000001', '{"tv"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000143-0000-4000-8000-000000000001', 'Double Burner Gas Cooker', 'gas-cooker-double', null, '{"burners": "2"}'::jsonb,
  'd00000034-0000-4000-8000-000000000001', ''{}'', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000144-0000-4000-8000-000000000001', 'Queen Size Mattress', 'mattress-queen', null, '{"size": "queen"}'::jsonb,
  'd00000044-0000-4000-8000-000000000001', '{"bed"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000145-0000-4000-8000-000000000001', 'Office Desk L-Shape', 'desk-l-shape', null, '{"shape": "L"}'::jsonb,
  'd00000047-0000-4000-8000-000000000001', '{"desk"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000146-0000-4000-8000-000000000001', 'A4 Copy Paper Ream', 'a4-paper-ream', null, '{"sheets": "500"}'::jsonb,
  'd00000045-0000-4000-8000-000000000001', '{"paper"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000147-0000-4000-8000-000000000001', 'Lusaka Comedy Night Ticket', 'comedy-night-lsk', null, '{"venue": "Lusaka"}'::jsonb,
  'd00000062-0000-4000-8000-000000000001', '{"comedy"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000148-0000-4000-8000-000000000001', 'Gospel Concert Ticket', 'gospel-concert', null, '{"genre": "gospel"}'::jsonb,
  'd00000063-0000-4000-8000-000000000001', '{"music"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000149-0000-4000-8000-000000000001', 'Community Clean-up RSVP', 'cleanup-rsvp', null, '{"price": "free"}'::jsonb,
  'd00000066-0000-4000-8000-000000000001', '{"rsvp"}', 'active'
) on conflict (id) do nothing;
insert into public.products (id, name, slug, brand, spec, category_id, aliases, status)
values (
  'p00000150-0000-4000-8000-000000000001', 'Cultural Dance Festival Pass', 'dance-festival', null, '{"type": "festival"}'::jsonb,
  'd00000065-0000-4000-8000-000000000001', '{"cultural"}', 'active'
) on conflict (id) do nothing;

commit;
