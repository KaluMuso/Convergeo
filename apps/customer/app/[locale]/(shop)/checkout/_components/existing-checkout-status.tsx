"use client";

import { createApiClient } from "@vergeo/config";
import { useEffect, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { useSession } from "../../../../../lib/customer-session";

// Read-only status for an existing ?session=/?group= handoff. Its own module so
// the cart checkout's first-load JS never carries it (bundle-guard).

type ExistingSessionStatus = {
  session_id: string;
  status: string;
  expires_at: string;
  expired: boolean;
};

export type ExistingCheckoutStatusProps = {
  groupId: string | null;
  labels: {
    title: string;
    loading: string;
    error: string;
    expired: string;
    statusTemplate: string;
    pending: string;
    completed: string;
    payment: string;
    unavailable: string;
  };
};

export function ExistingCheckoutStatus({ groupId, labels }: ExistingCheckoutStatusProps) {
  const { session, loading } = useSession();
  const accessToken = session?.access_token;
  const [result, setResult] = useState<{
    groupId: string;
    accessToken: string;
    data: ExistingSessionStatus | null;
  } | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!groupId || loading || !accessToken) return;
    let cancelled = false;
    const baseUrl = getApiBaseUrl();
    if (!baseUrl?.trim()) {
      setResult({ groupId, accessToken, data: null });
      return;
    }
    const client = createApiClient({ baseUrl, getToken: () => accessToken });
    // This ownership-checked GET is read-only. Payment-options can expire a group
    // through a write, so it and all payment/order actions are excluded here.
    void client
      .request<ExistingSessionStatus>(`/checkout/session/${encodeURIComponent(groupId)}`, {
        method: "GET",
      })
      .then((data) => {
        if (
          !data ||
          typeof data.session_id !== "string" ||
          data.session_id.toLowerCase() !== groupId.toLowerCase() ||
          !["pending", "completed", "abandoned", "expired"].includes(data.status) ||
          typeof data.expired !== "boolean" ||
          typeof data.expires_at !== "string" ||
          !Number.isFinite(Date.parse(data.expires_at))
        )
          throw new Error("Invalid checkout status response");
        if (!cancelled) setResult({ groupId, accessToken, data });
      })
      .catch(() => {
        if (!cancelled) setResult({ groupId, accessToken, data: null });
      });
    return () => {
      cancelled = true;
    };
  }, [groupId, loading, accessToken]);

  // Never display a previous identifier's or signed-in user's result while a
  // new retrieval is pending. The backend remains the ownership authority.
  const current =
    result?.groupId === groupId && result?.accessToken === accessToken ? result : null;
  const failed = !groupId || (!loading && !accessToken) || current?.data === null;
  const data = current?.data;

  useEffect(() => {
    if (loading || !data || data.expired || ["expired", "abandoned"].includes(data.status)) return;
    const expiresAt = Date.parse(data.expires_at);
    let timer: ReturnType<typeof setTimeout> | undefined;
    const updateExpiry = () => {
      const timestamp = Date.now();
      setNow(timestamp);
      const remaining = expiresAt - timestamp;
      if (remaining > 0) timer = setTimeout(updateExpiry, Math.min(remaining, 2_147_483_647));
    };
    updateExpiry();
    return () => {
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [data, loading]);

  const expired =
    data &&
    (data.expired ||
      ["expired", "abandoned"].includes(data.status) ||
      Date.parse(data.expires_at) <= Math.max(now, Date.now()));

  return (
    <section className="space-y-4 rounded-lg border p-6">
      <h1 className="text-2xl font-semibold">{labels.title}</h1>
      <p role={failed ? "alert" : "status"}>
        {failed
          ? labels.error
          : loading || !data
            ? labels.loading
            : expired
              ? labels.expired
              : labels.statusTemplate.replace(
                  "{status}",
                  data.status === "completed" ? labels.completed : labels.pending,
                )}
      </p>
      <p>
        {labels.payment}: {labels.unavailable}
      </p>
    </section>
  );
}
