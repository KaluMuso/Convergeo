"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { useTranslations } from "next-intl";
import { useCallback, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";
import { useSession } from "../../../../../../lib/customer-session";

type RequestFreeServiceProps = {
  locale: string;
  serviceId: string;
};

/**
 * Free-service CTA: no quote, no payment. Sends a booking request the vendor
 * accepts or declines. One idempotency key per attempt so retries never duplicate.
 */
export function RequestFreeService({ serviceId }: RequestFreeServiceProps) {
  const t = useTranslations("services.freeBooking");
  const { session } = useSession();
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);
  const getToken = useCallback(
    () => session?.access_token ?? null,
    [session?.access_token],
  );

  const handleRequest = useCallback(async () => {
    if (!session) {
      setError(t("errors.authRequired"));
      return;
    }
    setSubmitting(true);
    setError(null);
    idempotencyKeyRef.current ??= crypto.randomUUID();
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
      await client.request(`/services/${serviceId}/request-free`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: idempotencyKeyRef.current }),
      });
      setSent(true);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 401
          ? t("errors.authRequired")
          : status === 409
            ? t("errors.alreadyRequested")
            : status === 429
              ? t("errors.rateLimited")
              : t("errors.generic"),
      );
    } finally {
      setSubmitting(false);
    }
  }, [session, t, getToken, serviceId]);

  return (
    <section className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-1">
      <header className="space-y-1">
        <h3 className="font-display text-h3 text-display-ink">{t("title")}</h3>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {sent ? (
        <p
          className="rounded bg-success/10 p-3 text-sm font-semibold text-success"
          role="status"
        >
          {t("sent")}
        </p>
      ) : (
        <Button
          type="button"
          variant="primary"
          loading={submitting}
          loadingLabel={t("submitting")}
          disabled={submitting}
          onClick={() => void handleRequest()}
        >
          {t("cta")}
        </Button>
      )}
    </section>
  );
}
