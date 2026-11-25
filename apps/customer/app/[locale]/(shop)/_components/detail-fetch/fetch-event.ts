import { createApiClient } from "@vergeo/config";
import { absoluteApiUrl, getApiBaseUrl } from "../../../../../lib/api-base-url";
export type EventDetailPayload = Record<string, unknown> & {
  id: string;
  slug: string;
  title: string;
  is_free: boolean;
  is_sold_out: boolean;
  min_price_ngwee: number | null;
  visibility?: string;
  instances: Array<{ id: string; starts_at: string; ends_at: string | null }>;
  ticket_types: unknown[];
  images: string[];
  organiser: { display_name: string; slug: string };
};
export type EventFetchResult =
  | { kind: "event"; data: EventDetailPayload }
  | { kind: "not_found" }
  | { kind: "unavailable" }
  | { kind: "private_access" };
export async function fetchEventDetail(
  slug: string,
  options: { accessProof?: string | null; privateGate?: boolean } = {},
): Promise<EventFetchResult> {
  const url = absoluteApiUrl(`/events/${encodeURIComponent(slug)}`);
  if (!url) return { kind: "unavailable" };
  const accessProof = options.accessProof ?? null;
  const init = accessProof
    ? { cache: "no-store" as const, headers: { "X-Event-Access": accessProof } }
    : { next: { revalidate: 300, tags: [`event:${slug}`, "events"] } };
  try {
    const response = await fetch(url, init);
    if (response.status === 404)
      return options.privateGate ? { kind: "private_access" } : { kind: "not_found" };
    if (response.status === 401 || response.status === 403) return { kind: "private_access" };
    if (!response.ok) return { kind: "unavailable" };
    return { kind: "event", data: (await response.json()) as EventDetailPayload };
  } catch {
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl() });
      const headers = accessProof ? { "X-Event-Access": accessProof } : undefined;
      return {
        kind: "event",
        data: await client.request(`/events/${encodeURIComponent(slug)}`, { headers }),
      };
    } catch (error) {
      const status =
        typeof error === "object" && error && "status" in error
          ? (error as { status: number }).status
          : null;
      if (status === 404)
        return options.privateGate ? { kind: "private_access" } : { kind: "not_found" };
      if (status === 401 || status === 403) return { kind: "private_access" };
      return { kind: "unavailable" };
    }
  }
}
