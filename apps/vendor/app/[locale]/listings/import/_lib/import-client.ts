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

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export async function importCsv(
  file: File,
  getToken: () => string | null | Promise<string | null>,
): Promise<ImportSummary> {
  const baseUrl = getApiBaseUrl().replace(/\/$/, "");
  const headers = new Headers({
    "Content-Type": "text/csv; charset=utf-8",
  });
  const token = await getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

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
