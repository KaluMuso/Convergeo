export const SOURCE_TABS = ["suppliers", "made_in_zambia", "import", "services"] as const;
export type SourceTab = (typeof SOURCE_TABS)[number];
export const DEFAULT_TAB: SourceTab = "suppliers";
export const PAGE_SIZE = 12;

/** Message key (under vendor.source.tabs) for each tab. */
export const TAB_LABEL_KEY: Record<SourceTab, string> = {
  suppliers: "tabs.suppliers",
  made_in_zambia: "tabs.madeInZambia",
  import: "tabs.import",
  services: "tabs.services",
};

export type PriceTier = { min_qty: number; price_ngwee: number };

export type SourcingItem = {
  kind: "listing" | "shop" | "service";
  id: string;
  title: string;
  image_public_id: string | null;
  image_url: string | null;
  price_ngwee: number | null;
  price_tiers: PriceTier[] | null;
  /** Bulk/tier prices exist but the viewer is below KYC tier 2: the API withheld them. */
  prices_locked: boolean;
  moq: number | null;
  wholesale: boolean;
  made_in_zambia: boolean;
  vendor_id: string;
  shop_name: string;
  shop_slug: string | null;
  landmark: string | null;
  verified: boolean;
  whatsapp_msisdn: string | null;
  supplier_types: string[];
  service_category: string | null;
};

export type SourcingSearchResponse = {
  tab: "suppliers" | "made_in_zambia" | "services";
  viewer_verified: boolean;
  items: SourcingItem[];
  next_offset: number | null;
};

export type MizStatus = "claimed" | "approved" | "rejected";

export type SupplierType = "wholesaler" | "manufacturer" | "importer" | "service_provider";
export const SUPPLIER_TYPES: readonly SupplierType[] = [
  "wholesaler",
  "manufacturer",
  "importer",
  "service_provider",
];

export function parseTab(value: string | null | undefined): SourceTab {
  return (SOURCE_TABS as readonly string[]).includes(value ?? "")
    ? (value as SourceTab)
    : DEFAULT_TAB;
}

export type SourceUrlState = { tab: SourceTab; q: string; category: string };

/** Query string for the page URL; defaults are omitted so the default view stays `/source`. */
export function buildPageQuery(state: SourceUrlState): string {
  const params = new URLSearchParams();
  if (state.tab !== DEFAULT_TAB) params.set("tab", state.tab);
  if (state.q.trim()) params.set("q", state.q.trim());
  if (state.category) params.set("category", state.category);
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** API path for a search tab (not used for the import tab). */
export function buildSearchPath(state: SourceUrlState, offset: number): string {
  const params = new URLSearchParams();
  params.set("tab", state.tab === "import" ? DEFAULT_TAB : state.tab);
  if (state.q.trim()) params.set("q", state.q.trim());
  if (state.category) params.set("category", state.category);
  if (offset > 0) params.set("offset", String(offset));
  params.set("limit", String(PAGE_SIZE));
  return `/vendor/sourcing/search?${params.toString()}`;
}

/** wa.me deep link from the stored E.164-without-plus msisdn; null when unusable. */
export function whatsappLink(msisdn: string | null, text: string): string | null {
  if (!msisdn || !/^\d{9,15}$/.test(msisdn)) return null;
  return `https://wa.me/${msisdn}?text=${encodeURIComponent(text)}`;
}

/** Tiers sorted by quantity, for display. */
export function sortedTiers(tiers: PriceTier[] | null): PriceTier[] {
  return [...(tiers ?? [])].sort((a, b) => a.min_qty - b.min_qty);
}

export function categoryEnabled(tab: SourceTab): boolean {
  return tab === "suppliers" || tab === "made_in_zambia";
}
