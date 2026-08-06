"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useCallback, useMemo, useState } from "react";

import { createRfqApiClient, RFQ_DETAILS_MAX_CHARS } from "../../../../../lib/rfq-api";

export type RequestQuoteStatus = "idle" | "sending" | "success" | "error";

export type UseRequestQuoteResult = {
  sessionReady: boolean;
  isSignedIn: boolean;
  status: RequestQuoteStatus;
  errorKey: string | null;
  reusedExistingThread: boolean;
  threadId: string | null;
  maxDetailsChars: number;
  submitRequest: (payload: {
    listingId?: string;
    serviceId?: string;
    details: string;
  }) => Promise<boolean>;
  reset: () => void;
};

function mapError(error: unknown): string {
  if (error instanceof ApiError) {
    const code = error.code ?? "";
    if (code === "rfq.prohibited_content") {
      return "prohibited";
    }
    if (code.includes("rate") || code === "rate_limited") {
      return "rateLimited";
    }
    if (code === "rfq.own_listing") {
      return "ownListing";
    }
    if (code === "unauthorized" || code === "auth.required") {
      return "signInRequired";
    }
    if (error.status === 401) {
      return "signInRequired";
    }
  }
  return "generic";
}

export function useRequestQuote(): UseRequestQuoteResult {
  const { session, loading } = useSession();
  const [status, setStatus] = useState<RequestQuoteStatus>("idle");
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [reusedExistingThread, setReusedExistingThread] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const rfqClient = useMemo(() => createRfqApiClient(getToken), [getToken]);

  const reset = useCallback(() => {
    setStatus("idle");
    setErrorKey(null);
    setReusedExistingThread(false);
    setThreadId(null);
  }, []);

  const submitRequest = useCallback(
    async (payload: { listingId?: string; serviceId?: string; details: string }) => {
      const trimmed = payload.details.trim();
      if (!trimmed) {
        setErrorKey("empty");
        setStatus("error");
        return false;
      }
      if (trimmed.length > RFQ_DETAILS_MAX_CHARS) {
        setErrorKey("tooLong");
        setStatus("error");
        return false;
      }
      if (!session?.access_token) {
        setErrorKey("signInRequired");
        setStatus("error");
        return false;
      }

      setStatus("sending");
      setErrorKey(null);
      try {
        const response = await rfqClient.createRfq({
          listing_id: payload.listingId,
          service_id: payload.serviceId,
          requested_details: trimmed,
        });
        setReusedExistingThread(response.reused_existing_thread);
        setThreadId(response.thread.id);
        setStatus("success");
        return true;
      } catch (error) {
        setErrorKey(mapError(error));
        setStatus("error");
        return false;
      }
    },
    [rfqClient, session?.access_token],
  );

  return {
    sessionReady: !loading,
    isSignedIn: Boolean(session?.access_token),
    status,
    errorKey,
    reusedExistingThread,
    threadId,
    maxDetailsChars: RFQ_DETAILS_MAX_CHARS,
    submitRequest,
    reset,
  };
}
