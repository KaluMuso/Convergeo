// Vendor-portal fixtures: "Mwila's Phone Hub", an approved Lusaka electronics
// seller on Cairo Road. Money is integer ngwee (K1,250.00 = 125000).

const VENDOR_ID = "5a1e0000-0000-4000-8000-000000000101";
const BUSINESS_ID = "5a1e0000-0000-4000-8000-000000000201";
const BRANCH_ID = VENDOR_ID;
const SHOP = "Mwila's Phone Hub";
const CLOUDINARY = "https://res.cloudinary.com/convergeo/image/upload";

const ago = (minutes) => new Date(Date.now() - minutes * 60_000).toISOString();
const lusakaToday = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Lusaka" }).format(new Date());

// ---- Orders -------------------------------------------------------------
const ORDERS = [
  {
    id: "0d000000-0000-4000-8000-000000001041",
    status: "placed",
    fulfilment: "delivery",
    total_ngwee: 389900,
    item_count: 1,
    preview_title: "Samsung Galaxy A15 128GB",
    minutesAgo: 18,
    available_actions: ["confirm", "reject"],
    urgency: 3,
  },
  {
    id: "0d000000-0000-4000-8000-000000001040",
    status: "placed",
    fulfilment: "pickup",
    total_ngwee: 45000,
    item_count: 2,
    preview_title: "Anker 20W USB-C charger",
    minutesAgo: 52,
    available_actions: ["confirm", "reject"],
    urgency: 2,
  },
  {
    id: "0d000000-0000-4000-8000-000000001038",
    status: "confirmed",
    fulfilment: "delivery",
    total_ngwee: 129900,
    item_count: 1,
    preview_title: "Tecno Spark 20 Pro screen protector + case",
    minutesAgo: 140,
    available_actions: ["pack"],
    urgency: 2,
  },
  {
    id: "0d000000-0000-4000-8000-000000001036",
    status: "processing",
    fulfilment: "pickup",
    total_ngwee: 249900,
    item_count: 1,
    preview_title: "Itel 10,000mAh solar power bank",
    minutesAgo: 260,
    available_actions: ["ready_for_pickup"],
    urgency: 1,
  },
  {
    id: "0d000000-0000-4000-8000-000000001031",
    status: "shipped",
    fulfilment: "delivery",
    total_ngwee: 1150000,
    item_count: 1,
    preview_title: "HP 250 G9 laptop (refurbished)",
    minutesAgo: 1500,
    available_actions: [],
    urgency: 0,
  },
  {
    id: "0d000000-0000-4000-8000-000000001027",
    status: "completed",
    fulfilment: "pickup",
    total_ngwee: 72500,
    item_count: 3,
    preview_title: "Oraimo FreePods 4 earbuds",
    minutesAgo: 4300,
    available_actions: [],
    urgency: 0,
  },
];

const queueItem = ({ minutesAgo, ...order }) => ({ ...order, created_at: ago(minutesAgo) });
const NEEDS_ACTION = new Set(["placed", "confirmed", "processing"]);

function queueCounts() {
  const counts = { all: ORDERS.length, needs_action: 0, placed: 0, confirmed: 0, processing: 0, ready: 0, shipped: 0 };
  for (const order of ORDERS) {
    if (order.status in counts) counts[order.status] += 1;
    if (NEEDS_ACTION.has(order.status)) counts.needs_action += 1;
  }
  return counts;
}

function queue({ url }) {
  const status = url.searchParams.get("status") ?? "needs_action";
  const rows = ORDERS.filter((order) => {
    if (status === "all") return true;
    if (status === "needs_action") return NEEDS_ACTION.has(order.status);
    return order.status === status;
  });
  return rows.map(queueItem);
}

const dashboard = () => ({
  takings_ngwee: 434900,
  takings_date: lusakaToday(),
  needs_action: ORDERS.filter((order) => NEEDS_ACTION.has(order.status)).map(queueItem),
  queue_counts: queueCounts(),
  archetype: "electronics",
  business_archetype: "registered_retailer",
});

// ---- KYC ----------------------------------------------------------------
const KYC_STATUS = {
  application_status: "approved",
  vendor_status: "active",
  kyc_tier: 2,
  kyc_record_id: "c0c00000-0000-4000-8000-000000000301",
  kyc_record_status: "approved",
  tier: 2,
  doc_storage_paths: [`${VENDOR_ID}/nrc-front.jpg`, `${VENDOR_ID}/selfie.jpg`],
  momo_name_match: { matched: true, score: 0.96 },
  reviewer_notes: null,
  archetype: "electronics",
  business_archetype: "registered_retailer",
  business_name: SHOP,
  created: false,
  vendor_id: VENDOR_ID,
};

// ---- Listings -----------------------------------------------------------
const listing = (id, title, price, extra = {}) => ({
  id: `11500000-0000-4000-8000-00000000${id}`,
  title,
  price_ngwee: price,
  compare_at_ngwee: null,
  product_class: "standard",
  sale_unit: "each",
  unit_step_milli: 1000,
  min_steps: 1,
  condition: "new",
  defect_notes: null,
  condition_detail: null,
  fulfilment_options: ["delivery", "pickup"],
  fulfilment_mode: "in_stock",
  lead_time_days: null,
  vendor_capacity_per_week: null,
  stock_mode: "tracked",
  stock_qty: 6,
  wholesale: false,
  price_tiers: null,
  moq: 1,
  returnable: true,
  return_window_hours: 72,
  status: "active",
  product_id: null,
  images: [
    {
      id: `1a900000-0000-4000-8000-00000000${id}`,
      cloudinary_public_id: extra.image ?? "demo/categories/mobile-phones",
      position: 0,
    },
  ],
  ...extra,
});

const LISTINGS = [
  listing("0401", "Samsung Galaxy A15 128GB — Blue Black", 389900, { compare_at_ngwee: 419900, stock_qty: 8 }),
  listing("0402", "Tecno Spark 20 Pro 256GB", 329900, { stock_qty: 5 }),
  listing("0403", "HP 250 G9 laptop, Core i5, 8GB/512GB (refurbished)", 1150000, {
    condition: "used",
    condition_detail: "like_new",
    stock_qty: 2,
    image: "demo/categories/laptops-computers",
  }),
  listing("0404", "Itel 10,000mAh solar power bank", 249900, {
    stock_qty: 14,
    image: "demo/categories/solar-power",
  }),
  listing("0405", "Anker 20W USB-C fast charger", 22500, { stock_mode: "always_available", stock_qty: null }),
  listing("0406", "Oraimo FreePods 4 wireless earbuds", 72500, { status: "paused", stock_qty: 0 }),
  listing("0407", "iPhone 13 128GB (UK used, grade A)", 899900, {
    status: "draft",
    condition: "used",
    condition_detail: "good",
    stock_qty: 1,
  }),
];

// ---- Plan ---------------------------------------------------------------
const plan = (key, name, price, maxListings, extra = {}) => ({
  key,
  name,
  price_ngwee: price,
  annual_price_ngwee: Math.floor(price * 12 * 0.85),
  max_listings: maxListings,
  max_images_per_listing: 8,
  featured_slots: 0,
  analytics_depth: "basic",
  wholesale_tools: false,
  ...extra,
});
const PLANS = [
  plan("free", "Free", 0, 20),
  plan("starter", "Starter", 4900, 200, { featured_slots: 1 }),
  plan("business", "Business", 14900, null, { featured_slots: 3, analytics_depth: "full", wholesale_tools: true }),
  plan("pro", "Pro", 39900, null, { featured_slots: 10, analytics_depth: "full", wholesale_tools: true }),
];
const PLAN_STATUS = {
  enabled: true,
  plan: PLANS[2],
  effective_max_listings: null,
  max_images_per_listing: 8,
  listing_count: LISTINGS.length,
  remaining_listings: null,
  at_limit: false,
  over_limit: false,
  limited_by: "none",
  override_expires_at: null,
  upgrade_options: [PLANS[3]],
  plans: PLANS,
  annual_discount_pct: 15,
  trial_ends_at: "2027-01-15T21:59:59Z",
  in_trial: true,
};

// ---- Businesses ---------------------------------------------------------
const BUSINESSES = {
  enabled: true,
  businesses: [
    {
      id: BUSINESS_ID,
      legal_name: "Mwila Banda Trading Ltd",
      registration_type: "company",
      pacra_number: "120230045678",
      pacra_verified: true,
      status: "active",
      owner_kyc_approved: true,
      staff_seats: 3,
      staff_used: 1,
      allowance: {
        registered: true,
        plan_key: "business",
        included_shops: 2,
        extra_shop_price_ngwee: 4900,
        used: 1,
        limit: 2,
        can_add: true,
        next_billing_role: "included",
        next_price_ngwee: null,
        blocked_reason: null,
      },
      branches: [
        {
          id: BRANCH_ID,
          slug: "mwilas-phone-hub",
          display_name: `${SHOP} — Cairo Road`,
          status: "active",
          branch_status: "approved",
          branch_kind: "physical",
          is_primary: true,
          payout_on_hold: false,
          review_note: null,
        },
      ],
    },
  ],
};

// ---- Profile ------------------------------------------------------------
const day = (open, close) => ({ open, close });
const PROFILE = {
  vendor_id: VENDOR_ID,
  slug: "mwilas-phone-hub",
  display_name: SHOP,
  description:
    "Genuine smartphones, laptops and accessories on Cairo Road, Lusaka. Every phone is tested in-store, comes with a 6-month warranty, and you can pay with MTN or Airtel Money.",
  logo_url: `${CLOUDINARY}/c_fill,w_256,h_256,f_auto,q_auto/demo/categories/mobile-phones`,
  cover_url: `${CLOUDINARY}/c_fill,w_1200,h_400,f_auto,q_auto/demo/categories/laptops-computers`,
  whatsapp_msisdn: "260971234567",
  preferred_badge: true,
  kyc_tier: 2,
  status: "active",
  hours: {
    mon: day("08:00", "18:00"),
    tue: day("08:00", "18:00"),
    wed: day("08:00", "18:00"),
    thu: day("08:00", "18:00"),
    fri: day("08:00", "18:30"),
    sat: day("09:00", "16:00"),
    sun: { closed: true },
  },
  lat: -15.4167,
  lng: 28.2833,
  landmark: "Cairo Road, opposite Findeco House, next to Zanaco",
  slug_locked: false,
  previous_slug: null,
  completeness_score: 100,
  completeness: { logo: true, description: true, hours: true, location: true, badge: true },
  brand_theme: { primary: null, accent: null },
};

// ---- Payouts ------------------------------------------------------------
const PAYOUTS = {
  escrow_held_ngwee: 389900 + 129900 + 249900 + 1150000,
  released_available_ngwee: 218450,
  paid_out_ngwee: 4_862_300,
  payouts_blocked: false,
  payouts_paused: false,
  payout_hold_until: null,
  payout_msisdn: "260971234567",
  payout_rail: "mtn",
};
const PAYOUT_HISTORY = [
  [1_245_000, "paid", 60 * 24 * 2, "1119"],
  [879_500, "paid", 60 * 24 * 9, "1102"],
  [312_800, "processing", 60 * 3, "1124"],
  [1_530_000, "paid", 60 * 24 * 16, "1087"],
  [95_000, "failed", 60 * 24 * 20, "1079"],
  [1_207_800, "paid", 60 * 24 * 23, "1071"],
]
  .sort((a, b) => a[2] - b[2])
  .map(([amount, status, minutesAgo, seq]) => ({
    id: `9a900000-0000-4000-8000-00000000${seq}`,
    amount_ngwee: amount,
    rail: "mtn",
    status,
    lenco_reference: `pay-v101-${seq}`,
    created_at: ago(minutesAgo),
  }));

// ---- Analytics ----------------------------------------------------------
const ANALYTICS_SUMMARY = {
  window_days: 30,
  total_views: 3184,
  total_orders: 47,
  gmv_ngwee: 6_412_300,
  impressions: 2410,
  pdp_views: 774,
};

function analytics({ url }) {
  const window = Number(url.searchParams.get("window")) === 7 ? 7 : 30;
  const days = [];
  const sales = [];
  const orders = [];
  const activity = [];
  for (let i = window - 1; i >= 0; i -= 1) {
    days.push(new Date(Date.now() - i * 86_400_000).toISOString().slice(0, 10));
    const n = (i * 7 + 3) % 5;
    orders.push(n);
    sales.push(n * 128_500 + ((i * 3) % 4) * 22_500);
    activity.push(12 + ((i * 11) % 17));
  }
  const ordersTotal = orders.reduce((a, b) => a + b, 0);
  const eventsTotal = activity.reduce((a, b) => a + b, 0);
  return {
    window,
    days,
    sales_ngwee_by_day: sales,
    orders_by_day: orders,
    cart_activity_events_by_day: activity,
    order_activity_ratio: {
      orders_total: ordersTotal,
      cart_activity_events_total: eventsTotal,
      orders_per_100_cart_activity_events: Math.round((ordersTotal / eventsTotal) * 1000) / 10,
    },
    views_by_day: activity,
    top_listings: LISTINGS.slice(0, 4).map((row, index) => ({
      listing_id: row.id,
      title: row.title,
      units: 9 - index * 2,
      revenue_ngwee: row.price_ngwee * (9 - index * 2),
    })),
    conversion_hint: {
      orders_total: ordersTotal,
      views_total: eventsTotal,
      conversion_pct: Math.round((ordersTotal / eventsTotal) * 1000) / 10,
    },
  };
}

// ---- Notifications ------------------------------------------------------
const NOTIFICATIONS = {
  items: [
    {
      id: "e0000000-0000-4000-8000-000000000501",
      type: "order_placed",
      i18n_key: "notifications.vendor.order_placed",
      params: { order_ref: "1041", amount: "K3,899.00" },
      link_path: `/orders/${ORDERS[0].id}`,
      created_at: ago(18),
      seen: false,
      read: false,
    },
    {
      id: "e0000000-0000-4000-8000-000000000502",
      type: "order_placed",
      i18n_key: "notifications.vendor.order_placed",
      params: { order_ref: "1040", amount: "K450.00" },
      link_path: `/orders/${ORDERS[1].id}`,
      created_at: ago(52),
      seen: false,
      read: false,
    },
    {
      id: "e0000000-0000-4000-8000-000000000503",
      type: "payout_paid",
      i18n_key: "notifications.vendor.payout_paid",
      params: { amount: "K12,450.00" },
      link_path: "/payouts",
      created_at: ago(60 * 24 * 2),
      seen: true,
      read: true,
    },
  ],
  next_cursor: null,
};

export const vendorFixtures = [
  // Anonymous server-side nav probes: 200 means "router registered".
  ["GET", "/rfq", { items: [] }],
  ["GET", "/jobs", { items: [] }],
  ["GET", "/vendor/pickup/verify", { detail: "Method Not Allowed" }],

  ["GET", "/me/notifications/unseen-count", { unseen: 2 }],
  // Shared with the other portals: only answer for the vendor audience.
  [
    "GET",
    "/me/notifications",
    ({ url }) =>
      url.searchParams.get("audience") === "vendor" ? NOTIFICATIONS : { items: [], next_cursor: null },
  ],

  ["GET", "/kyc/status", KYC_STATUS],
  ["POST", "/kyc/bootstrap", KYC_STATUS],

  ["GET", "/vendor/plan", PLAN_STATUS],
  ["GET", "/vendor/businesses", BUSINESSES],
  ["GET", "/vendor/profile", PROFILE],

  ["GET", "/vendor/orders/dashboard", dashboard],
  ["GET", "/vendor/orders/queue", queue],

  ["GET", "/vendor/listings", LISTINGS],

  ["GET", "/vendor/analytics/summary", ANALYTICS_SUMMARY],
  ["GET", "/vendor/analytics", analytics],

  ["GET", "/vendor/payouts", PAYOUTS],
  ["GET", "/vendor/payouts/history", { items: PAYOUT_HISTORY }],
];
