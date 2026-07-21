"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

export type ConfirmReceivedLabels = {
  title: string;
  body: string;
  trust: string;
  button: string;
  confirming: string;
  done: string;
  doneBody: string;
  error: string;
};

type ConfirmReceivedBlockProps = {
  orderId: string;
  accessToken: string;
  status: string;
  labels: ConfirmReceivedLabels;
};

type ConfirmResponse = {
  order_id: string;
  status: "completed";
  already_confirmed: boolean;
};

export function ConfirmReceivedBlock({
  orderId,
  accessToken,
  status,
  labels,
}: ConfirmReceivedBlockProps) {
  const router = useRouter();
  const [confirmed, setConfirmed] = useState(status === "completed");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const canConfirm = status === "delivered" && !confirmed;

  const handleConfirm = useCallback(async () => {
    if (!canConfirm || submitting) {
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      const response = await client.request<ConfirmResponse>(
        `/orders/${orderId}/confirm-received`,
        { method: "POST" },
      );
      if (response.status === "completed") {
        setConfirmed(true);
        router.refresh();
      }
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(labels.error);
      } else {
        setError(labels.error);
      }
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, canConfirm, labels.error, orderId, router, submitting]);

  if (status !== "delivered" && status !== "completed") {
    return null;
  }

  return (
    <section
      aria-labelledby="confirm-received-heading"
      className="space-y-3 rounded border border-border bg-surface p-4"
    >
      <h3 id="confirm-received-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>

      {confirmed ? (
        <div className="space-y-1">
          <p className="text-sm font-medium text-display-ink">{labels.done}</p>
          <p className="text-sm text-text-2">{labels.doneBody}</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-text-2">{labels.body}</p>
          <p className="rounded bg-bg-2 px-3 py-2 text-sm text-display-ink">{labels.trust}</p>
          {error ? (
            <p className="text-sm text-error" role="alert">
              {error}
            </p>
          ) : null}
          <Button
            type="button"
            className="min-h-11 w-full"
            disabled={!canConfirm || submitting}
            loading={submitting}
            loadingLabel={labels.confirming}
            onClick={() => void handleConfirm()}
          >
            {labels.button}
          </Button>
        </>
      )}
    </section>
  );
}
