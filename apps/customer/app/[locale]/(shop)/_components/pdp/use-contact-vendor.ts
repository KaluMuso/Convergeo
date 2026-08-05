"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useCallback, useMemo, useState } from "react";

import {
  createEnquiriesApiClient,
  ENQUIRY_BODY_MAX_CHARS,
  type CreateEnquiryResponse,
} from "../../../../../lib/enquiries-api";

export type ContactVendorStatus = "idle" | "sending" | "success" | "error";

export type UseContactVendorResult = {
  sessionReady: boolean;
  isSignedIn: boolean;
  status: ContactVendorStatus;
  errorKey: string | null;
  reusedExistingThread: boolean;
  maxBodyChars: number;
  sendMessage: (listingId: string, body: string) => Promise<CreateEnquiryResponse | null>;
  reset: () => void;
};

/**
 * Hook for the PDP "Contact vendor" flow. Uses the authenticated FastAPI
 * enquiry endpoint — listing-anchored C2B only (D37).
 */
export function useContactVendor(): UseContactVendorResult {
  const { session, loading: sessionLoading } = useSession();
  const [status, setStatus] = useState<ContactVendorStatus>("idle");
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [reusedExistingThread, setReusedExistingThread] = useState(false);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const client = useMemo(() => createEnquiriesApiClient(getToken), [getToken]);

  const reset = useCallback(() => {
    setStatus("idle");
    setErrorKey(null);
    setReusedExistingThread(false);
  }, []);

  const sendMessage = useCallback(
    async (listingId: string, body: string) => {
      const trimmed = body.trim();
      if (!trimmed) {
        setStatus("error");
        setErrorKey("empty");
        return null;
      }
      if (trimmed.length > ENQUIRY_BODY_MAX_CHARS) {
        setStatus("error");
        setErrorKey("tooLong");
        return null;
      }
      if (!session?.access_token) {
        setStatus("error");
        setErrorKey("signInRequired");
        return null;
      }

      setStatus("sending");
      setErrorKey(null);
      try {
        const response = await client.createEnquiry({
          subject_kind: "listing",
          subject_id: listingId,
          body: trimmed,
        });
        setReusedExistingThread(response.reused_existing_thread);
        setStatus("success");
        return response;
      } catch (err) {
        setStatus("error");
        if (err instanceof ApiError) {
          if (err.code === "enquiry.prohibited_content") {
            setErrorKey("prohibited");
          } else if (err.code === "rate_limited" || err.code === "enquiries.errors.rateLimited") {
            setErrorKey("rateLimited");
          } else if (err.code === "enquiry.own_subject") {
            setErrorKey("ownListing");
          } else {
            setErrorKey("generic");
          }
        } else {
          setErrorKey("generic");
        }
        return null;
      }
    },
    [client, session?.access_token],
  );

  return {
    sessionReady: !sessionLoading,
    isSignedIn: Boolean(session?.access_token),
    status,
    errorKey,
    reusedExistingThread,
    maxBodyChars: ENQUIRY_BODY_MAX_CHARS,
    sendMessage,
    reset,
  };
}
