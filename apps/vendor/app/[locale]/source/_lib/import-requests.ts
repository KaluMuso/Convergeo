export type ImportStatus = "submitted" | "in_review" | "quoted" | "closed" | "cancelled";

export type ImportQuote = {
  id: string;
  request_id: string;
  partner_label: string | null;
  product_ngwee: number;
  freight_ngwee: number;
  duty_ngwee: number;
  clearing_ngwee: number;
  other_ngwee: number;
  total_ngwee: number;
  lead_time_days: number | null;
  valid_until: string | null;
  notes: string | null;
  is_estimate: boolean;
  created_at: string;
};

export type ImportRequest = {
  id: string;
  title: string;
  description: string | null;
  reference_url: string | null;
  image_urls: string[];
  quantity: number;
  unit: string;
  target_unit_price_ngwee: number | null;
  destination_city: string | null;
  status: ImportStatus;
  created_at: string;
  updated_at: string;
  latest_quote: ImportQuote | null;
};

export type ImportFormValues = {
  title: string;
  description: string;
  referenceUrl: string;
  imageUrls: string;
  quantity: string;
  unit: string;
  targetPrice: string;
  destination: string;
};

export const EMPTY_FORM: ImportFormValues = {
  title: "",
  description: "",
  referenceUrl: "",
  imageUrls: "",
  quantity: "",
  unit: "pcs",
  targetPrice: "",
  destination: "",
};

/** Kwacha text ("35", "35.50") to integer ngwee without floating point; null when invalid. */
export function kwachaToNgwee(text: string): number | null {
  const match = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(text.trim());
  if (!match) return null;
  const whole = Number(match[1]);
  const cents = Number((match[2] ?? "").padEnd(2, "0"));
  return whole * 100 + cents;
}

/** Request body for `POST /vendor/sourcing/import-requests`, or null when the form is invalid. */
export function toRequestBody(values: ImportFormValues): Record<string, unknown> | null {
  const quantity = Number(values.quantity);
  if (!Number.isInteger(quantity) || quantity < 1) return null;
  if (values.title.trim().length < 3) return null;
  const images = values.imageUrls
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const body: Record<string, unknown> = {
    title: values.title.trim(),
    quantity,
    unit: values.unit.trim() || "pcs",
    image_urls: images,
  };
  if (values.description.trim()) body.description = values.description.trim();
  if (values.referenceUrl.trim()) body.reference_url = values.referenceUrl.trim();
  if (values.destination.trim()) body.destination_city = values.destination.trim();
  if (values.targetPrice.trim()) {
    const ngwee = kwachaToNgwee(values.targetPrice);
    if (ngwee === null || ngwee <= 0) return null;
    body.target_unit_price_ngwee = ngwee;
  }
  return body;
}

export const OPEN_STATUSES: ReadonlySet<ImportStatus> = new Set([
  "submitted",
  "in_review",
  "quoted",
]);
