export type ListingMode = "attach" | "new_canonical" | "quick_list";

export type ListingCondition = "new" | "refurbished";
export type StockMode = "tracked" | "always_available";

export type CommissionPreview = {
  category_key: string;
  rate_bps: number;
  rate_percent: number;
};

export type CanonicalPreview = {
  product_id: string;
  name: string;
  brand: string | null;
  spec: Record<string, unknown>;
  category_id: string;
  category_name: string;
  commission: CommissionPreview;
};

export type CategoryOption = {
  id: string;
  name: string;
  commission_key: string;
  commission: CommissionPreview;
};

export type SuggestItem = {
  title: string;
  entity_kind: string;
  entity_id: string;
};

export type PriceTierInput = {
  min_qty: number;
  price_ngwee: number;
};

export type ListingCreatePayload = {
  mode: ListingMode;
  product_id?: string | null;
  product_name?: string;
  brand?: string | null;
  spec?: Record<string, unknown>;
  category_id?: string;
  aliases?: string[];
  title_override?: string;
  price_ngwee: number;
  condition: ListingCondition;
  stock_mode: StockMode;
  stock_qty?: number | null;
  wholesale?: boolean;
  price_tiers?: PriceTierInput[];
  moq?: number;
  returnable?: boolean;
  return_window_hours?: number | null;
  publish?: boolean;
};

export type ListingCreateResponse = {
  listing_id: string;
  mode: ListingMode;
  status: string;
  product_id: string | null;
  product_status: string | null;
  commission: CommissionPreview | null;
};
