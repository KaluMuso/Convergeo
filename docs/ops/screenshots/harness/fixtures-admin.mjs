// Admin console fixtures (superadmin view of a Lusaka marketplace). Money is integer ngwee.
const NOW = Date.now();
const ago = (hours) => new Date(NOW - hours * 3_600_000).toISOString();
const SELF = "00000000-0000-4000-8000-000000000001";

const ALL_PERMISSIONS = [
  "finance.read",
  "finance.operate",
  "events.manage",
  "products.manage",
  "services.read",
  "services.manage",
  "vendors.manage",
  "ads.manage",
  "analytics.read",
  "inventory.read",
  "support.manage",
  "logistics.manage",
  "cod.reconcile",
  "audit.read",
];

const vid = (n) => `0b1e0000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`;
const kid = (n) => `0c2f0000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`;
const oid = (n) => `0d3a0000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`;
const cid = (n) => `0e4b0000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`;

// [display, slug, vendor_status, kyc_tier, kyc_record_status, tier, age_hours, sla]
const VENDOR_ROWS = [
  ["Chanda Electronics", "chanda-electronics", "pending", 0, "submitted", 2, 52, "overdue"],
  ["Mama Bupe's Kitchen", "mama-bupes-kitchen", "pending", 0, "submitted", 1, 30, "due_soon"],
  ["Kitwe Hardware Depot", "kitwe-hardware-depot", "pending", 1, "submitted", 2, 20, "on_track"],
  ["Ndola Fresh Farms", "ndola-fresh-farms", "pending", 0, "submitted", 1, 9, "on_track"],
  ["Kabulonga Beauty Bar", "kabulonga-beauty-bar", "pending", 0, "submitted", 1, 4, "on_track"],
  ["Cairo Road Phones", "cairo-road-phones", "active", 2, "approved", 2, null, null],
  ["Levy Junction Books", "levy-junction-books", "active", 1, "approved", 1, null, null],
  ["Livingstone Crafts Co.", "livingstone-crafts", "suspended", 1, "approved", 1, null, null],
  ["Chilenje Tailors", "chilenje-tailors", "rejected", 0, "rejected", 1, null, null],
  ["Soweto Market Traders", "soweto-market-traders", "active", 1, "approved", 1, null, null],
  ["Ndeke Auto Spares", "ndeke-auto-spares", "active", 2, "approved", 2, null, null],
  ["Northmead Grocers", "northmead-grocers", "active", 1, "approved", 1, null, null],
  ["Copperbelt Outfitters", "copperbelt-outfitters", "active", 2, "approved", 2, null, null],
];

const vendors = VENDOR_ROWS.map(([display_name, slug, vendor_status, kyc_tier, kyc_record_status, tier, age, sla], i) => ({
  vendor_id: vid(i + 1),
  kyc_record_id: kid(i + 1),
  display_name,
  slug,
  vendor_status,
  kyc_tier,
  kyc_record_status,
  tier,
  updated_at: ago(age ?? 24 * (i + 2)),
  sla_badge: sla,
  age_hours: age,
}));

const disputes = [
  {
    id: "0f5c0000-0000-4000-8000-000000000001",
    order_id: oid(24),
    status: "open",
    vendor_display_name: "Cairo Road Phones",
    vendor_slug: "cairo-road-phones",
    customer_phone: "+260971000214",
    order_total_ngwee: 345000,
    created_at: ago(60),
    updated_at: ago(6),
    sla_badge: "overdue",
    age_hours: 60,
  },
  {
    id: "0f5c0000-0000-4000-8000-000000000002",
    order_id: oid(25),
    status: "awaiting_vendor",
    vendor_display_name: "Levy Junction Books",
    vendor_slug: "levy-junction-books",
    customer_phone: "+260966000381",
    order_total_ngwee: 42500,
    created_at: ago(18),
    updated_at: ago(3),
    sla_badge: "due_soon",
    age_hours: 18,
  },
  {
    id: "0f5c0000-0000-4000-8000-000000000003",
    order_id: oid(26),
    status: "open",
    vendor_display_name: "Ndeke Auto Spares",
    vendor_slug: "ndeke-auto-spares",
    customer_phone: "+260955000127",
    order_total_ngwee: 128000,
    created_at: ago(5),
    updated_at: ago(1),
    sla_badge: "on_track",
    age_hours: 5,
  },
];

// [vendor index, status, fulfilment, phone, hours ago]
const ORDER_ROWS = [
  [5, "placed", "delivery", "+260971000452", 0.6],
  [9, "confirmed", "delivery", "+260966000918", 2.2],
  [6, "processing", "pickup", "+260955000733", 4.5],
  [10, "ready", "delivery", "+260977000164", 6],
  [5, "shipped", "delivery", "+260962000585", 20],
  [11, "delivered", "delivery", "+260971000276", 30],
  [12, "completed", "pickup", "+260966000349", 72],
  [9, "cancelled", "delivery", "+260955000801", 50],
  [11, "placed", "delivery", "+260977000538", 1.1],
  [12, "placed", "pickup", "+260962000117", 1.7],
  [10, "placed", "delivery", "+260971000690", 2.4],
];

const orders = ORDER_ROWS.map(([v, status, fulfilment, customer_phone, h], i) => ({
  id: oid(i + 1),
  status,
  fulfilment,
  vendor_id: vendors[v].vendor_id,
  vendor_display_name: vendors[v].display_name,
  vendor_slug: vendors[v].slug,
  customer_id: cid(i + 1),
  customer_phone,
  created_at: ago(h),
}));

const zones = [
  { zone_key: "lusaka-central", label: "Lusaka Central (CBD, Rhodes Park)", fee_ngwee: 3500 },
  { zone_key: "lusaka-east", label: "Lusaka East (Kabulonga, Woodlands)", fee_ngwee: 4500 },
  { zone_key: "lusaka-west", label: "Lusaka West (Matero, Chunga)", fee_ngwee: 5000 },
  { zone_key: "lusaka-south", label: "Lusaka South (Chilenje, Kabwata)", fee_ngwee: 4000 },
];

const couriers = [
  {
    id: "0a6d0000-0000-4000-8000-000000000001",
    name: "Kwacha Riders",
    contact_whatsapp_e164: "+260971000900",
    contact_email: "dispatch@kwacha-riders.example.invalid",
    integration_kind: "manual",
    active: true,
    notes: "Motorbikes, CBD and east. Cash cap K2,000 per rider.",
    zones: [
      { zone_key: "lusaka-central", price_ngwee: 3000 },
      { zone_key: "lusaka-east", price_ngwee: 4000 },
      { zone_key: "lusaka-south", price_ngwee: 3500 },
    ],
  },
  {
    id: "0a6d0000-0000-4000-8000-000000000002",
    name: "Chongwe Express",
    contact_whatsapp_e164: "+260966000900",
    contact_email: null,
    integration_kind: "manual",
    active: true,
    notes: null,
    zones: [
      { zone_key: "lusaka-west", price_ngwee: 4500 },
      { zone_key: "lusaka-central", price_ngwee: 3200 },
    ],
  },
];

const readyOrders = [
  {
    order_id: oid(4),
    order_reference: "ord-K7Q2M4",
    status: "ready",
    vendor_name: "Ndeke Auto Spares",
    delivery_zone: "lusaka-east",
    cod: false,
    cod_amount_ngwee: 0,
    subtotal_ngwee: 89000,
    delivery_fee_ngwee: 4500,
    item_count: 3,
    created_at: ago(6),
    last_failed_reason: null,
    dropoff_landmark: "Opposite Kabulonga Shopping Centre",
    dropoff_area: "Kabulonga",
    ready_at: ago(1),
    pickup_label: "Kalingalinga branch",
    pickup_area: "Kalingalinga",
    delivery_attempts: 0,
  },
  {
    order_id: oid(20),
    order_reference: "ord-P3X8L1",
    status: "ready",
    vendor_name: "Northmead Grocers",
    delivery_zone: "lusaka-central",
    cod: true,
    cod_amount_ngwee: 27500,
    subtotal_ngwee: 24000,
    delivery_fee_ngwee: 3500,
    item_count: 2,
    created_at: ago(3),
    last_failed_reason: null,
    dropoff_landmark: "Near Levy Junction Mall, gate 2",
    dropoff_area: "Rhodes Park",
    ready_at: ago(0.5),
    pickup_label: "Northmead",
    pickup_area: "Northmead",
    delivery_attempts: 0,
  },
];

const baseDispatch = {
  courier_reference: null,
  pod_photo_public_id: null,
  delivered_via: null,
  failure_reason: null,
  notify_count: 1,
  accepted_at: null,
  picked_up_at: null,
  delivered_at: null,
  failed_at: null,
  cancelled_at: null,
  handover_locked: false,
  attempt_no: 1,
  failure_code: null,
  actual_cost_ngwee: null,
  cod_collected_ngwee: null,
  cod_collected_method: null,
  remitted: false,
  door_payment_state: null,
};

const dispatches = [
  {
    ...baseDispatch,
    id: "0b7e0000-0000-4000-8000-000000000001",
    order_id: oid(5),
    order_reference: "ord-M9D4T6",
    courier_partner_id: couriers[0].id,
    courier_name: couriers[0].name,
    status: "picked_up",
    allowed_next: ["delivered", "failed"],
    cod_amount_ngwee: 0,
    quoted_price_ngwee: 4000,
    last_notified_at: ago(2),
    requested_at: ago(4),
    accepted_at: ago(3.5),
    picked_up_at: ago(2),
    vendor_name: "Cairo Road Phones",
    order_status: "shipped",
    delivery_zone: "lusaka-east",
    handover_locked: true,
  },
  {
    ...baseDispatch,
    id: "0b7e0000-0000-4000-8000-000000000002",
    order_id: oid(21),
    order_reference: "ord-R2C7W5",
    courier_partner_id: couriers[1].id,
    courier_name: couriers[1].name,
    status: "accepted",
    allowed_next: ["picked_up", "cancelled"],
    cod_amount_ngwee: 61000,
    quoted_price_ngwee: 4500,
    last_notified_at: ago(1),
    requested_at: ago(1.5),
    accepted_at: ago(1),
    vendor_name: "Levy Junction Books",
    order_status: "ready",
    delivery_zone: "lusaka-west",
  },
  {
    ...baseDispatch,
    id: "0b7e0000-0000-4000-8000-000000000003",
    order_id: oid(6),
    order_reference: "ord-A5H1N8",
    courier_partner_id: couriers[0].id,
    courier_name: couriers[0].name,
    status: "delivered",
    allowed_next: [],
    cod_amount_ngwee: 0,
    quoted_price_ngwee: 3500,
    actual_cost_ngwee: 3500,
    last_notified_at: ago(26),
    requested_at: ago(28),
    accepted_at: ago(27.5),
    picked_up_at: ago(27),
    delivered_at: ago(25),
    delivered_via: "otp",
    vendor_name: "Northmead Grocers",
    order_status: "delivered",
    delivery_zone: "lusaka-south",
    handover_locked: true,
  },
  {
    ...baseDispatch,
    id: "0b7e0000-0000-4000-8000-000000000004",
    order_id: oid(22),
    order_reference: "ord-T6B3E9",
    courier_partner_id: couriers[0].id,
    courier_name: couriers[0].name,
    status: "requested",
    allowed_next: ["accepted", "cancelled"],
    cod_amount_ngwee: 18500,
    quoted_price_ngwee: 3000,
    last_notified_at: ago(0.3),
    requested_at: ago(0.3),
    vendor_name: "Copperbelt Outfitters",
    order_status: "ready",
    delivery_zone: "lusaka-central",
  },
  {
    ...baseDispatch,
    id: "0b7e0000-0000-4000-8000-000000000005",
    order_id: oid(23),
    order_reference: "ord-W8F2J4",
    courier_partner_id: couriers[1].id,
    courier_name: couriers[1].name,
    status: "failed",
    allowed_next: [],
    cod_amount_ngwee: 0,
    quoted_price_ngwee: 4500,
    failure_reason: "Customer unreachable on +260 97x; gate locked at Matero address.",
    failure_code: "customer_unavailable",
    last_notified_at: ago(9),
    requested_at: ago(12),
    accepted_at: ago(11.5),
    picked_up_at: ago(11),
    failed_at: ago(9),
    vendor_name: "Soweto Market Traders",
    order_status: "shipped",
    delivery_zone: "lusaka-west",
  },
];

const dashboard = () => ({
  gmv_ngwee: 18_452_350,
  orders_by_status: {
    placed: 4,
    confirmed: 12,
    processing: 9,
    ready: 4,
    shipped: 6,
    delivered: 15,
    completed: 312,
    cancelled: 11,
  },
  payout_liabilities: {
    escrow_held_ngwee: 4_218_500,
    released_unpaid_ngwee: 1_376_250,
    total_ngwee: 5_594_750,
  },
  reconciliation: {
    status: "green",
    report_id: "0c8f0000-0000-4000-8000-000000000001",
    report_date: ago(20).slice(0, 10),
    has_mismatch: false,
    provenance: "VERSIONED_ACCOUNT_BOUND",
    evidence_state: "current_clean",
    version_number: 3,
    provider_account_id: "lenco-acct-0042",
    currency: "ZMW",
    certifiable: true,
    discrepancies: {},
  },
  finance_visible: true,
  counts: { vendors: 148, listings: 2364, products: 1180 },
  ai_usage: { data_available: true, flagged: false, killed: false, spend_usd: 4.82, cap_usd: 15 },
  funnel: {
    checkout_started: 1240,
    checkout_completed: 486,
    orders_placed: 452,
    orders_completed: 312,
  },
  cached_at: ago(0.1),
});

const accounts = [
  { user_id: SELF, display_name: "Mwila Banda", email: "mwila.banda@example.invalid", roles: ["superadmin"] },
  {
    user_id: "0a9a0000-0000-4000-8000-000000000002",
    display_name: "Natasha Mulenga",
    email: "natasha.mulenga@example.invalid",
    roles: ["admin"],
  },
  {
    user_id: "0a9a0000-0000-4000-8000-000000000003",
    display_name: "Joseph Phiri",
    email: "joseph.phiri@example.invalid",
    roles: ["finance"],
  },
  {
    user_id: "0a9a0000-0000-4000-8000-000000000004",
    display_name: "Grace Tembo",
    email: "grace.tembo@example.invalid",
    roles: ["kyc_reviewer", "support"],
  },
  {
    user_id: "0a9a0000-0000-4000-8000-000000000005",
    display_name: "Bwalya Zulu",
    email: "bwalya.zulu@example.invalid",
    roles: ["logistics"],
  },
  {
    user_id: "0a9a0000-0000-4000-8000-000000000006",
    display_name: "Chipo Sakala",
    email: "chipo.sakala@example.invalid",
    roles: ["catalog_moderator"],
  },
];

const DAY = 24;
const ahead = (hours) => new Date(NOW + hours * 3_600_000).toISOString();
// [legal_name, trial end (+ahead / -ago, days)]
const trials = [
  ["Ndeke Auto Spares Ltd", 24],
  ["Cairo Road Phones Ltd", -12],
  ["Copperbelt Outfitters (Kitwe) Ltd", 9],
  ["Levy Junction Books Ltd", -40],
  ["Soweto Market Traders Cooperative", 3],
  ["Chingola Copper Crafts", -5],
  ["Northmead Grocers Ltd", 17],
  ["Ndola Fresh Farms Ltd", 28],
].map(([legal_name, days], i) => ({
  business_id: `0a1b0000-0000-4000-8000-0000000000${String(i + 1).padStart(2, "0")}`,
  legal_name,
  trial_ends_at: days > 0 ? ahead(days * DAY) : ago(-days * DAY),
  in_trial: days > 0,
}));

export const adminFixtures = [
  [
    "GET",
    "/admin/trials",
    ({ url }) => {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      return q ? trials.filter((t) => t.legal_name.toLowerCase().includes(q)) : trials;
    },
  ],
  [
    "GET",
    "/admin/me/permissions",
    { user_id: SELF, permissions: ALL_PERMISSIONS, can_manage_roles: true, unrestricted: true },
  ],
  ["GET", "/admin/dashboard", dashboard],
  [
    "GET",
    "/admin/vendors",
    ({ url }) => {
      const status = url.searchParams.get("status");
      return status ? vendors.filter((v) => v.vendor_status === status) : vendors;
    },
  ],
  ["GET", "/admin/disputes", disputes],
  [
    "GET",
    "/admin/dispatch/board",
    { flag_enabled: true, door_payment_enabled: true, ready_orders: readyOrders, dispatches, couriers, zones },
  ],
  [
    "GET",
    "/admin/logistics/pricing-switches",
    { rain_mode: false, area_pricing_shadow: true, area_pricing_live: false },
  ],
  [
    "GET",
    "/admin/orders/search",
    ({ url }) => {
      const status = url.searchParams.get("status");
      return status ? orders.filter((o) => o.status === status) : orders;
    },
  ],
  ["GET", "/admin/accounts", { accounts }],
  ["GET", "/me/notifications/unseen-count", { unseen: 3 }],
  ["GET", "/me/notifications", { items: [], next_cursor: null }],
];
