"use client";

import { getBrowserAccessToken } from "@vergeo/auth";

import { getApiBaseUrl } from "./api-base-url";

export type ExportFailure = "permission" | "error";

export class AnalyticsExportError extends Error {
  constructor(readonly kind: ExportFailure) {
    super(kind);
  }
}

/**
 * Download one analytics report as CSV. The API re-checks the report's permission and
 * writes an audit row for every export (and every refused one).
 */
export async function downloadAnalyticsCsv(
  report: string,
  query: string,
  filename: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const token = await getBrowserAccessToken();
  const headers = new Headers({ Accept: "text/csv" });
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let response: Response;
  try {
    response = await fetchImpl(
      `${getApiBaseUrl().replace(/\/$/, "")}/admin/analytics/export?report=${report}&${query}`,
      { headers },
    );
  } catch {
    throw new AnalyticsExportError("error");
  }
  if (response.status === 401 || response.status === 403) {
    throw new AnalyticsExportError("permission");
  }
  if (!response.ok) {
    throw new AnalyticsExportError("error");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
