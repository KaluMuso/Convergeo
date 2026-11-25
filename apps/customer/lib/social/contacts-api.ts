import { getApiBaseUrl } from "../api-base-url";
import { getAccessToken } from "../engagement-api";

async function socialRequest<T>(path: string, init: RequestInit & { method?: string }): Promise<T> {
  const token = await getAccessToken();
  if (!token) {
    throw new Error("unauthenticated");
  }
  const response = await fetch(`${getApiBaseUrl().replace(/\/$/, "")}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(String(response.status));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export type PeopleCard = {
  user_id: string;
  handle: string;
  display_name: string | null;
  is_contact: boolean;
};

export type ContactRequest = {
  id: string;
  from_user: string;
  to_user: string;
  note: string | null;
  status: string;
  created_at: string;
  outgoing: boolean;
};

export type Contact = {
  user_id: string;
  handle: string | null;
  display_name: string | null;
  thread_id: string | null;
};

export type DiscoverMatch = {
  user_id: string;
  handle: string | null;
  display_name: string | null;
};

export type ChatMessage = {
  id: string;
  thread_id: string;
  sender: string;
  kind: string;
  body: string | null;
  card: Record<string, unknown> | null;
  created_at: string;
};

export const contactsApi = {
  listContacts: () => socialRequest<{ items: Contact[] }>("/contacts", { method: "GET" }),
  listRequests: (box: "in" | "out" | "all" = "all") =>
    socialRequest<{ items: ContactRequest[] }>(
      `/contacts/requests?box=${encodeURIComponent(box)}`,
      { method: "GET" },
    ),
  lookupHandle: (handle: string) =>
    socialRequest<PeopleCard>(`/people/${encodeURIComponent(handle)}`, { method: "GET" }),
  sendRequest: (to_handle: string, note?: string) =>
    socialRequest<{ request_id: string; status: string }>("/contacts/requests", {
      method: "POST",
      body: JSON.stringify({ to_handle, note }),
    }),
  acceptRequest: (id: string) =>
    socialRequest<{ thread_id: string | null }>(`/contacts/requests/${id}/accept`, {
      method: "POST",
    }),
  ignoreRequest: (id: string) =>
    socialRequest<unknown>(`/contacts/requests/${id}/ignore`, { method: "POST" }),
  blockUser: (userId: string) =>
    socialRequest<unknown>(`/contacts/${userId}/block`, { method: "POST" }),
  discoverHashes: (hashes: string[]) =>
    socialRequest<{ items: DiscoverMatch[] }>("/contacts/discover-phones", {
      method: "POST",
      body: JSON.stringify({ hashes }),
    }),
  getPhoneDiscovery: () =>
    socialRequest<{ enabled: boolean; pepper_configured: boolean }>("/me/phone-discovery", {
      method: "GET",
    }),
  setPhoneDiscovery: (enabled: boolean) =>
    socialRequest<{ enabled: boolean }>("/me/phone-discovery", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  getMyHandle: () => socialRequest<{ handle: string }>("/me/handle", { method: "GET" }),
  getQr: () =>
    socialRequest<{ handle: string; payload: string; share_path: string }>("/me/qr", {
      method: "GET",
    }),
  listMessages: (threadId: string) =>
    socialRequest<{ items: ChatMessage[] }>(`/chats/${threadId}/messages`, { method: "GET" }),
  sendMessage: (threadId: string, body: string) =>
    socialRequest<{ message_id: string }>(`/chats/${threadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ kind: "text", body }),
    }),
};
