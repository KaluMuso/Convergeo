import { ApiError } from "@vergeo/config";

export type RowImportResult = {
  row: number;
  ok: boolean;
  errors: string[];
  listing_id: string | null;
};

export type ImportSummary = {
  accepted: number;
  rejected: number;
  rows: RowImportResult[];
};

export type CanonicalSuggestion = {
  product_id: string;
  name: string;
  score: number;
};

export type RowPreview = {
  row: number;
  ok: boolean;
  errors: string[];
  sku: string | null;
  title: string | null;
  price_ngwee: number | null;
  product_id: string | null;
  matched_name: string | null;
  suggestions: CanonicalSuggestion[];
  raw: Record<string, string>;
};

export type ImportPreview = {
  total: number;
  valid: number;
  invalid: number;
  rows: RowPreview[];
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

async function authHeaders(
  getToken: () => string | null | Promise<string | null>,
  contentType: string,
): Promise<Headers> {
  const headers = new Headers({ "Content-Type": contentType });
  const token = await getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function postJson<T>(
  path: string,
  body: unknown,
  getToken: () => string | null | Promise<string | null>,
  errorCode: string,
): Promise<T> {
  const baseUrl = getApiBaseUrl().replace(/\/$/, "");
  const headers = await authHeaders(getToken, "application/json");
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network_error", "Network request failed", { status: 0 });
  }
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiError(errorCode, "Import request failed", { status: response.status });
  }
  return payload as T;
}

/** Dry-run: validate the CSV and return per-row status + canonical suggestions. */
export async function previewCsv(
  file: File,
  getToken: () => string | null | Promise<string | null>,
): Promise<ImportPreview> {
  const baseUrl = getApiBaseUrl().replace(/\/$/, "");
  const headers = await authHeaders(getToken, "text/csv; charset=utf-8");
  const csvText = await file.text();
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/listings/import/preview`, {
      method: "POST",
      headers,
      body: csvText,
    });
  } catch {
    throw new ApiError("network_error", "Network request failed", { status: 0 });
  }
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiError("preview_failed", "Preview request failed", { status: response.status });
  }
  return payload as ImportPreview;
}

/** Apply already-parsed rows (with confirmed product_ids) back to the server. */
export async function applyRawRows(
  rawRows: Record<string, string>[],
  getToken: () => string | null | Promise<string | null>,
): Promise<ImportSummary> {
  return postJson<ImportSummary>(
    "/listings/import",
    { raw_rows: rawRows },
    getToken,
    "import_failed",
  );
}

export async function importCsv(
  file: File,
  getToken: () => string | null | Promise<string | null>,
): Promise<ImportSummary> {
  const baseUrl = getApiBaseUrl().replace(/\/$/, "");
  const headers = await authHeaders(getToken, "text/csv; charset=utf-8");
  const csvText = await file.text();

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/listings/import`, {
      method: "POST",
      headers,
      body: csvText,
    });
  } catch {
    throw new ApiError("network_error", "Network request failed", { status: 0 });
  }

  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiError("import_failed", "Import request failed", { status: response.status });
  }

  return payload as ImportSummary;
}
