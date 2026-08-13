export type ListingMode = "attach" | "new_canonical" | "quick_list";

export type ProductClass = "A" | "B" | "C" | "D" | "E";
export type ListingCondition = "new" | "refurbished" | "used";
export type SaleUnit = "each" | "metre" | "kg" | "litre" | "bag" | "sqm";
export type FulfilmentMode = "stocked" | "made_to_order";
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
  product_class: ProductClass;
  sale_unit: SaleUnit;
  unit_step_milli: number;
  min_steps: number;
  condition: ListingCondition;
  defect_notes?: string | null;
  fulfilment_mode: FulfilmentMode;
  lead_time_days?: number | null;
  vendor_capacity_per_week?: number | null;
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
  requires_evidence?: boolean;
  next_action?: string | null;
};
