// Customer-portal screenshot fixtures. Money is integer ngwee (K1,250.00 = 125000).
// Image ids are seeded public ids in the `convergeo` Cloudinary cloud.

const IMG = (slug) => `demo/categories/${slug}`;

const daysAgo = (days, hour = 10) => {
  const date = new Date(Date.UTC(2026, 10, 25, hour, 15));
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString();
};

// ---------------------------------------------------------------- vendors

// Most seeded `demo/categories/*` photos do not show what their names say
// (e.g. `mobile-phones` is a street scene, `solar-power` a doorway), and
// `traditional-wear` is a "#WeAreAllMonkeys" cartoon that must never appear in
// a Zambian storefront capture. Only ids whose photo matches the title are used.
const PHOTO = {
  laptop: IMG("laptops-computers"),
  remote: IMG("tvs-audio"),
  fabric: IMG("chitenge-fabric"),
  cushions: IMG("furniture"),
  cosmetics: IMG("skincare"),
  stationery: IMG("paper-notebooks"),
  clayPot: IMG("kitchenware"),
  soupBowl: IMG("cooking-oil"),
  workshop: IMG("hand-tools"),
  street: IMG("mobile-phones"),
};

const VENDORS = [
  ["kabulonga-tech-hub", "Kabulonga Tech Hub", PHOTO.laptop, true, 3, "gold", "Opposite Kabulonga Mall, Lusaka", ["Laptops", "Accessories"], 4.8, 214, 86],
  ["cairo-road-electronics", "Cairo Road Electronics", PHOTO.remote, false, 2, "silver", "Cairo Road, near Findeco House", ["TV & Audio", "Repairs"], 4.6, 131, 142],
  ["sunshare-solar-zambia", "Sunshare Solar Zambia", null, true, 3, "platinum", "Great East Road, by Arcades", ["Solar", "Inverters"], 4.9, 97, 38],
  ["chitenge-house-lusaka", "Chitenge House Lusaka", PHOTO.fabric, false, 2, "silver", "Kamwala Market, Stand 42", ["Chitenge", "Tailoring"], 4.7, 76, 120],
  ["mama-bupe-kitchen-home", "Mama Bupe Kitchen & Home", PHOTO.clayPot, false, 1, "bronze", "Woodlands Shopping Centre", ["Kitchenware", "Home decor"], 4.5, 58, 64],
  ["northmead-stationers", "Northmead Stationers", PHOTO.stationery, false, 1, "bronze", "Northmead Market, Lusaka", ["Stationery", "Printing"], 4.3, 41, 210],
].map(([slug, name, logo, preferred, kyc, tier, landmark, categories, rating, count, listings], index) => ({
  id: `7a1c0000-0000-4000-8000-${String(101 + index).padStart(12, "0")}`,
  slug,
  display_name: name,
  logo_url: logo,
  preferred_badge: preferred,
  kyc_tier: kyc,
  commercial_tier: tier,
  verified: kyc >= 1,
  landmark,
  categories,
  rating_avg: rating,
  rating_count: count,
  listing_count: listings,
}));
const vendor = (slug) => VENDORS.find((entry) => entry.slug === slug);

// ---------------------------------------------------------------- listings

const listing = (n, title, slug, vendorSlug, price, image, extra = {}) => ({
  id: `11570000-0000-4000-8000-${String(n).padStart(12, "0")}`,
  title,
  product_slug: slug,
  vendor_name: vendor(vendorSlug).display_name,
  price_ngwee: price,
  compare_at_ngwee: null,
  condition: "new",
  in_stock: true,
  image_public_id: image,
  rating: 4.6,
  review_count: 12,
  distance_m: null,
  below_median: false,
  delivery_available: true,
  pickup_available: true,
  ...extra,
});

const LISTINGS = {
  laptop: listing(1, "HP 250 G9 Laptop, Core i5, 8GB / 512GB SSD", "hp-250-g9-core-i5", "kabulonga-tech-hub", 1149900, PHOTO.laptop, { compare_at_ngwee: 1249900, rating: 4.5, review_count: 23, below_median: true }),
  laptop2: listing(2, "Lenovo IdeaPad 3, Ryzen 5, 16GB / 512GB", "lenovo-ideapad-3-ryzen-5", "kabulonga-tech-hub", 1289900, PHOTO.laptop, { compare_at_ngwee: 1349900, rating: 4.6, review_count: 31 }),
  laptopUsed: listing(3, "Dell Latitude 5490, Core i5 (refurbished)", "dell-latitude-5490-refurb", "cairo-road-electronics", 549900, PHOTO.laptop, { condition: "refurbished", rating: 4.3, review_count: 18 }),
  remote: listing(4, "Universal Smart TV Remote, backlit", "universal-smart-tv-remote", "kabulonga-tech-hub", 25000, PHOTO.remote, { rating: 4.4, review_count: 57 }),
  fabric: listing(5, "Chitenge Fabric, 6 yards, wax print", "chitenge-fabric-6-yards", "chitenge-house-lusaka", 18000, PHOTO.fabric, { compare_at_ngwee: 22000, rating: 4.9, review_count: 140 }),
  dress: listing(6, "Chitenge Wrap Dress, hand-tailored", "chitenge-wrap-dress", "chitenge-house-lusaka", 45000, PHOTO.fabric, { rating: 4.8, review_count: 34, delivery_available: false }),
  tablecloth: listing(7, "Kitenge Print Tablecloth, 6-seater", "kitenge-tablecloth-6-seater", "chitenge-house-lusaka", 32000, PHOTO.fabric, { rating: 4.7, review_count: 21 }),
  cushions: listing(8, "Woven Throw Cushions, set of 4", "woven-throw-cushions-4", "mama-bupe-kitchen-home", 68000, PHOTO.cushions, { rating: 4.6, review_count: 26 }),
  clayPot: listing(9, "Hand-made Clay Cooking Pot, 5L", "clay-cooking-pot-5l", "mama-bupe-kitchen-home", 15500, PHOTO.clayPot, { rating: 4.8, review_count: 44, fulfilment_mode: "made_to_order" }),
  bowls: listing(10, "Ceramic Soup Bowls, set of 6", "ceramic-soup-bowls-6", "mama-bupe-kitchen-home", 27500, PHOTO.soupBowl, { compare_at_ngwee: 32000, rating: 4.5, review_count: 19 }),
  cosmetics: listing(11, "Body Cream & Soap Gift Trio", "body-cream-soap-trio", "mama-bupe-kitchen-home", 34000, PHOTO.cosmetics, { rating: 4.3, review_count: 28 }),
  stationery: listing(12, "Back-to-School Stationery Bundle", "back-to-school-stationery", "northmead-stationers", 22500, PHOTO.stationery, { rating: 4.4, review_count: 63 }),
};
const L = LISTINGS;

const NEWEST = [L.laptop, L.fabric, L.cushions, L.clayPot, L.laptop2, L.dress, L.remote, L.bowls];
const POPULAR = [L.stationery, L.fabric, L.laptopUsed, L.clayPot, L.cosmetics, L.tablecloth, L.remote, L.bowls, L.laptop, L.cushions, L.dress, L.laptop2];

// ---------------------------------------------------------------- categories
// Served by Supabase REST (`/rest/v1/categories`); other REST tables fall
// through to [] in mock-backend.mjs.

const CATEGORIES = [
  ["electronics", "Electronics"],
  ["fashion", "Fashion"],
  ["home-living", "Home & Living"],
  ["groceries-staples", "Groceries & Staples"],
  ["personal-care-beauty", "Personal Care & Beauty"],
  ["office-stationery", "Office & Stationery"],
  ["light-hardware", "Light Hardware"],
].map(([slug, name], index) => ({
  id: `ca7e0000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
  name,
  slug,
  path: slug.replace(/-/g, "_"),
  position: index + 1,
  parent_id: null,
  prohibited: false,
}));

const DEPARTMENT_LISTINGS = {
  electronics: [L.laptop, L.laptop2, L.laptopUsed, L.remote],
  fashion: [L.dress, L.fabric, L.tablecloth, L.cosmetics],
  "home-living": [L.cushions, L.clayPot, L.bowls, L.tablecloth],
};

// ---------------------------------------------------------------- services

const SERVICES = [
  ["laptop-phone-repair", "Laptop & phone repair, same day", "Cairo Road Electronics", 25000, PHOTO.workshop],
  ["chitenge-tailoring", "Custom chitenge tailoring", "Chitenge House Lusaka", 30000, PHOTO.fabric],
  ["lusaka-errands-delivery", "Same-day errands across Lusaka", "Kabulonga Tech Hub", 6000, PHOTO.street],
  ["interior-styling", "Living-room styling consult", "Mama Bupe Kitchen & Home", 80000, PHOTO.cushions],
  ["home-catering", "Home-cooked catering for 30 guests", "Mama Bupe Kitchen & Home", 270000, PHOTO.soupBowl],
  ["printing-binding", "Printing, binding & laminating", "Northmead Stationers", 1500, PHOTO.stationery],
].map(([slug, title, provider, from, image], index) => ({
  id: `5e7c0000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
  slug,
  title,
  from_price_ngwee: from,
  portfolio_images: [image],
  provider: { display_name: provider },
}));

// ---------------------------------------------------------------- deals

const DEALS = [
  [L.laptop, 1099900, 1249900],
  [L.fabric, 14500, 22000],
  [L.cushions, 54000, 68000],
  [L.laptop2, 1199900, 1349900],
  [L.bowls, 21900, 32000],
  [L.remote, 19900, 25000],
].map(([item, deal, reference], index) => ({
  deal_id: `dea10000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
  starts_at: daysAgo(1, 6),
  ends_at: "2026-11-27T21:59:00Z",
  deal_price_ngwee: deal,
  reference_price_ngwee: reference,
  discount_percent: Math.round(((reference - deal) / reference) * 100),
  listing: {
    id: item.id,
    title: item.title,
    product_slug: item.product_slug,
    vendor_name: item.vendor_name,
    price_ngwee: deal,
    condition: item.condition,
    in_stock: true,
    image_public_id: item.image_public_id,
    rating: item.rating,
    review_count: item.review_count,
    distance_m: null,
    delivery_available: item.delivery_available,
    pickup_available: item.pickup_available,
  },
}));

// ---------------------------------------------------------------- orders

const order = (n, vendorSlug, fields) => ({
  id: `0d0e0000-0000-4000-8000-${String(n).padStart(12, "0")}`,
  vendor_id: vendor(vendorSlug).id,
  vendor_name: vendor(vendorSlug).display_name,
  fulfilment: "delivery",
  cod: false,
  paid: true,
  payment_mode: "prepaid",
  discount_ngwee: 0,
  is_gift: false,
  ...fields,
});

const ORDER_GROUPS = [
  {
    checkout_group_id: "c6e00000-0000-4000-8000-000000000001",
    created_at: daysAgo(0, 8),
    orders: [
      // Paid with MTN MoMo, held in escrow until delivery.
      order(1, "sunshare-solar-zambia", { status: "confirmed", total_ngwee: 495000, item_count: 1, created_at: daysAgo(0, 8) }),
      // Courier on the way.
      order(2, "kabulonga-tech-hub", { status: "shipped", total_ngwee: 1159900, item_count: 1, created_at: daysAgo(0, 8) }),
    ],
  },
  {
    checkout_group_id: "c6e00000-0000-4000-8000-000000000002",
    created_at: daysAgo(6, 14),
    orders: [
      order(3, "chitenge-house-lusaka", { status: "delivered", fulfilment: "pickup", total_ngwee: 63000, item_count: 2, created_at: daysAgo(6, 14) }),
    ],
  },
  {
    checkout_group_id: "c6e00000-0000-4000-8000-000000000003",
    created_at: daysAgo(19, 11),
    orders: [
      order(4, "mama-bupe-kitchen-home", { status: "cancelled", cod: true, paid: false, payment_mode: "cod", total_ngwee: 78000, item_count: 1, created_at: daysAgo(19, 11) }),
    ],
  },
].map((group) => ({
  ...group,
  total_ngwee: group.orders.reduce((sum, entry) => sum + entry.total_ngwee, 0),
}));

const ALL_ORDERS = ORDER_GROUPS.flatMap((group) =>
  group.orders.map((entry) => ({ ...entry, checkout_group_id: group.checkout_group_id })),
);

const ORDER_ITEMS = {
  1: [{ title: "200W Solar Home Kit with 100Ah battery", qty: 1, unit_price_ngwee: 485000 }],
  2: [{ title: L.laptop.title, qty: 1, unit_price_ngwee: 1149900, variant_options: [{ group: "Colour", value: "Silver" }] }],
  3: [
    { title: L.dress.title, qty: 1, unit_price_ngwee: 45000, variant_options: [{ group: "Size", value: "M" }] },
    { title: L.fabric.title, qty: 1, unit_price_ngwee: 18000 },
  ],
  4: [{ title: L.cushions.title, qty: 1, unit_price_ngwee: 68000 }],
};

const TIMELINE_STEPS = ["placed", "paid", "confirmed", "shipped", "delivered"];

function orderDetail(id) {
  const summary = ALL_ORDERS.find((entry) => entry.id === id) ?? ALL_ORDERS[0];
  const n = Number(summary.id.slice(-12));
  const items = ORDER_ITEMS[n].map((item, index) => ({
    id: `${summary.id.slice(0, -2)}${String(index + 10)}`,
    variant_options: [],
    variant_sku: null,
    ...item,
  }));
  const subtotal = items.reduce((sum, item) => sum + item.qty * item.unit_price_ngwee, 0);
  const reached = { confirmed: 2, shipped: 3, delivered: 4, cancelled: 0 }[summary.status] ?? 0;
  return {
    ...summary,
    delivery_fee_ngwee: summary.total_ngwee - subtotal,
    subtotal_ngwee: subtotal,
    items,
    timeline: TIMELINE_STEPS.map((step, index) => ({
      step_key: step,
      state:
        summary.status === "cancelled"
          ? index === 0 ? "completed" : "skipped"
          : index < reached ? "completed" : index === reached ? "current" : "upcoming",
      occurred_at: index <= reached ? summary.created_at : null,
      escrow_copy_key: summary.payment_mode === "cod" ? "cod" : summary.status === "delivered" ? "released" : "held",
    })),
    pickup: null,
    invoice: { invoice_id: null, download_url: null, stub: true },
    related_orders: ALL_ORDERS.filter(
      (entry) => entry.checkout_group_id === summary.checkout_group_id && entry.id !== summary.id,
    ),
  };
}

// ---------------------------------------------------------------- cart

const cartLine = (n, item, vendorSlug, qty, extra = {}) => ({
  id: `ca470000-0000-4000-8000-${String(n).padStart(12, "0")}`,
  listing_id: item.id,
  vendor_id: vendor(vendorSlug).id,
  qty,
  unit_price_ngwee: item.price_ngwee,
  wholesale: false,
  line_total_ngwee: item.price_ngwee * qty,
  title_override: item.title,
  sale_unit: "each",
  fulfilment_mode: "stocked",
  lead_time_days: null,
  is_rfq_quote: false,
  listing_variant_id: null,
  variant_options: [],
  ...extra,
});

const CART_LINES = [
  cartLine(1, L.laptop, "kabulonga-tech-hub", 1, { variant_options: [{ group: "Colour", value: "Silver" }] }),
  cartLine(2, L.remote, "kabulonga-tech-hub", 1),
  cartLine(3, L.fabric, "chitenge-house-lusaka", 3, { variant_options: [{ group: "Pattern", value: "Blue Kalindula" }] }),
];

const cartGroup = (vendorSlug, deliveryEligible) => {
  const items = CART_LINES.filter((line) => line.vendor_id === vendor(vendorSlug).id);
  return {
    vendor_id: vendor(vendorSlug).id,
    vendor_name: vendor(vendorSlug).display_name,
    items,
    subtotal_ngwee: items.reduce((sum, line) => sum + line.line_total_ngwee, 0),
    delivery_eligible: deliveryEligible,
    gifts: [],
    savings_ngwee: 0,
  };
};

const CART = {
  cart_id: "ca470000-0000-4000-8000-0000000000aa",
  items: CART_LINES,
  vendor_groups: [cartGroup("kabulonga-tech-hub", true), cartGroup("chitenge-house-lusaka", false)],
  subtotal_ngwee: CART_LINES.reduce((sum, line) => sum + line.line_total_ngwee, 0),
  ticket_lines: [],
  unavailable_ticket_line_ids: [],
  platform_fee_ngwee: 0,
  cod_allowed: false,
  conflicts: [],
  notices: [],
  savings_ngwee: 0,
};

// ---------------------------------------------------------------- wishlist

const WISHLIST = {
  items: [L.laptop2, L.cushions, L.tablecloth].map((item, index) => ({
    product_id: `9d0d0000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    slug: item.product_slug,
    name: item.title,
    created_at: daysAgo(index + 2),
  })),
};

// ---------------------------------------------------------------- routes

export const customerFixtures = [
  // Home: catalogue BFF (newest, department rails, services, vendors).
  [
    "GET",
    "/discovery/home",
    ({ url }) => {
      const paths = (url.searchParams.get("department_paths") ?? "").split(",").filter(Boolean);
      return {
        newest: { items: NEWEST },
        services: { items: SERVICES },
        vendors: { items: VENDORS },
        trending: { items: [] },
        department_rails: paths.map((path) => {
          const category = CATEGORIES.find((entry) => entry.path === path);
          return {
            category_path: path,
            listings: { items: DEPARTMENT_LISTINGS[category?.slug] ?? NEWEST.slice(0, 4) },
          };
        }),
      };
    },
  ],
  // Legacy fan-out and the mega-menu "new arrivals" preview.
  [
    "GET",
    "/catalog/listings",
    ({ url }) => {
      const limit = Number(url.searchParams.get("limit") ?? 24);
      const path = url.searchParams.get("category_path");
      const category = CATEGORIES.find((entry) => entry.path === path);
      const items = category ? (DEPARTMENT_LISTINGS[category.slug] ?? []) : Object.values(L);
      return { items: items.slice(0, limit), total: items.length, next_cursor: null };
    },
  ],
  ["GET", "/services", { items: SERVICES, total: SERVICES.length }],
  ["GET", "/directory", { items: VENDORS, total: VENDORS.length, page: 1, page_size: 48 }],
  ["GET", "/deals", { server_time: new Date().toISOString(), items: DEALS }],
  // Admin-governed feed left empty (no sections, no sponsored carousel) so the
  // default catalogue rails render and no ad creatives appear.
  ["GET", "/home/feed", { sections: [], carousel: [], next_cursor: null }],
  // "Popular now" stream: first page only.
  [
    "GET",
    "/home/stream",
    ({ url }) => (url.searchParams.get("cursor") ? { items: [], next_cursor: null } : { items: POPULAR, next_cursor: null }),
  ],
  ["GET", "/rest/v1/categories", CATEGORIES],
  [
    "GET",
    "/public/config/storefront",
    {
      free_delivery_threshold_ngwee: 150000,
      low_stock_threshold: 5,
      coupons_enabled: false,
      gift_orders_enabled: false,
      birthday_greetings_enabled: false,
    },
  ],

  // Signed-in chrome.
  ["GET", "/me/notifications/unseen-count", { unseen: 2 }],
  ["GET", "/account/wishlist", WISHLIST],
  ["PUT", "/account/wishlist", WISHLIST],
  ["POST", "/account/recently-viewed", { ok: true }],

  // Orders.
  ["GET", "/account/orders", { groups: ORDER_GROUPS }],
  ["GET", /^\/account\/orders\/([^/]+)$/, ({ match }) => orderDetail(match[1])],
  ["GET", /^\/account\/orders\/[^/]+\/delivery$/, { enabled: false, dispatch: null }],

  // Cart (server-side; no localStorage needed).
  [
    "GET",
    "/cart",
    ({ signedIn }) =>
      signedIn ? CART : { ...CART, items: [], vendor_groups: [], subtotal_ngwee: 0 },
  ],
  ["POST", "/cart/merge", { merged: false, cart_id: CART.cart_id }],
  ["POST", "/cart/revalidate", { notices: [], has_changes: false }],

  [
    "GET",
    "/search",
    ({ url }) => {
      const query = url.searchParams.get("q") ?? "";
      const hits = [L.laptop, L.laptop2, L.laptopUsed].map((item, index) => ({
        id: `5ea70000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
        entity_kind: "product",
        entity_id: item.id,
        title: item.title,
        body: `Sold by ${item.vendor_name}`,
        category_path: "electronics/laptops",
        price_min_ngwee: item.price_ngwee,
        price_max_ngwee: item.compare_at_ngwee ?? item.price_ngwee,
        lat: null,
        lng: null,
        locale_terms: null,
        boost_signals: { image_public_id: item.image_public_id },
        rrf_score: 1 - index * 0.1,
        slug: item.product_slug,
      }));
      return {
        query,
        expanded_query: query,
        page: 1,
        page_size: 20,
        total: hits.length,
        results: hits,
        degraded: false,
        facets: { categories: [{ value: "electronics/laptops", count: hits.length }], price: [] },
        kind_totals: { all: hits.length, products: hits.length, services: 0, events: 0, vendors: 0 },
      };
    },
  ],
  ["POST", "/telemetry/frontend-errors", { accepted: true }],
  ["POST", "/telemetry/views", { accepted: true }],
  ["POST", "/analytics/collect", { accepted: true }],
];
