"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Spinner } from "@vergeo/ui/src/spinner";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

type TicketSummary = {
  id: string;
  status: "issued" | "checked_in" | "transferred" | "void";
  event: {
    id: string;
    title: string;
    venue: string | null;
    slug: string;
  };
  instance: {
    id: string;
    starts_at: string;
  };
};

type TicketTransfer = {
  id: string;
  ticket_id: string;
  to_phone: string;
  status: "pending" | "claimed" | "cancelled" | "expired";
  expires_at: string;
  created_at: string;
};

function createTransferClient(getToken: () => string | null) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    getTicket(ticketId: string): Promise<TicketSummary> {
      return client.request<TicketSummary>(`/account/tickets/${ticketId}`);
    },
    getCurrentTransfer(ticketId: string): Promise<{ transfer: TicketTransfer | null }> {
      return client.request<{ transfer: TicketTransfer | null }>(`/tickets/${ticketId}/transfer`);
    },
    initiateTransfer(ticketId: string, toPhone: string): Promise<{ transfer: TicketTransfer }> {
      return client.request<{ transfer: TicketTransfer }>(`/tickets/${ticketId}/transfer`, {
        method: "POST",
        body: JSON.stringify({ to_phone: toPhone }),
      });
    },
    cancelTransfer(transferId: string): Promise<{ transfer: TicketTransfer }> {
      return client.request<{ transfer: TicketTransfer }>(
        `/tickets/transfers/${transferId}/cancel`,
        { method: "POST" },
      );
    },
  };
}

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export default function TransferTicketPage({ params }: PageProps) {
  const [locale, setLocale] = useState("en");
  const [ticketId, setTicketId] = useState("");
  const t = useTranslations("events.transfer");
  const { session, loading: sessionLoading } = useSession();
  const [ticket, setTicket] = useState<TicketSummary | null>(null);
  const [pending, setPending] = useState<TicketTransfer | null>(null);
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void params.then(({ locale: nextLocale, id }) => {
      setLocale(nextLocale);
      setTicketId(id);
    });
  }, [params]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const transferClient = useMemo(() => createTransferClient(getToken), [getToken]);

  const load = useCallback(async () => {
    if (!ticketId) {
      return;
    }
    setLoading(true);
    try {
      const [ticketData, transferData] = await Promise.all([
        transferClient.getTicket(ticketId),
        transferClient.getCurrentTransfer(ticketId),
      ]);
      setTicket(ticketData);
      setPending(transferData.transfer);
      setError(null);
    } catch {
      setError(t("errors.generic"));
    } finally {
      setLoading(false);
    }
  }, [ticketId, transferClient, t]);

  useEffect(() => {
    if (sessionLoading || !ticketId) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void load();
  }, [ticketId, load, session, sessionLoading]);

  const mapApiError = useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
        switch (err.code) {
          case "ticket_transfer_pending_exists":
            return t("errors.pendingExists");
          case "ticket_transfer_cutoff_passed":
            return t("errors.cutoffPassed");
          case "ticket_transfer_not_pending":
            return t("errors.notPending");
          case "ticket_not_transferable":
            return t("errors.notTransferable");
          case "forbidden":
            return t("errors.notHolder");
          case "not_found":
            return t("errors.notFound");
          case "rate_limited":
            return t("errors.rateLimited");
          default:
            return err.message || t("errors.generic");
        }
      }
      return t("errors.generic");
    },
    [t],
  );

  const handleSubmit = useCallback(async () => {
    setError(null);
    setMessage(null);
    const trimmed = phone.trim();
    if (!trimmed) {
      return;
    }
    setSubmitting(true);
    try {
      const result = await transferClient.initiateTransfer(ticketId, trimmed);
      setPending(result.transfer);
      setMessage(t("successBody", { phone: result.transfer.to_phone }));
      setPhone("");
    } catch (err) {
      setError(mapApiError(err));
    } finally {
      setSubmitting(false);
    }
  }, [mapApiError, phone, t, ticketId, transferClient]);

  const handleCancel = useCallback(async () => {
    if (!pending) {
      return;
    }
    setError(null);
    setMessage(null);
    setSubmitting(true);
    try {
      await transferClient.cancelTransfer(pending.id);
      setPending(null);
      setMessage(t("cancelledNotice"));
    } catch (err) {
      setError(mapApiError(err));
    } finally {
      setSubmitting(false);
    }
  }, [mapApiError, pending, t, transferClient]);

  if (sessionLoading || loading) {
    return (
      <section className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("title")} />
      </section>
    );
  }

  if (!session) {
    return (
      <p className="text-sm text-text-2">
        <Link href={`/${locale}/login`} className="font-semibold text-primary">
          {t("title")}
        </Link>
      </p>
    );
  }

  if (!ticket) {
    return <p className="text-sm text-danger">{error ?? t("errors.notFound")}</p>;
  }

  const startsAt = new Date(ticket.instance.starts_at).toLocaleString(locale, {
    dateStyle: "full",
    timeStyle: "short",
  });
  const cutoffMs = new Date(ticket.instance.starts_at).getTime() - 6 * 60 * 60 * 1000;
  const cutoffPassed = Date.now() > cutoffMs;
  const transferable = ticket.status === "issued" && !cutoffPassed;

  return (
    <section className="space-y-5">
      <Link
        href={`/${locale}/account/tickets/${ticketId}`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
      >
        {t("back")}
      </Link>

      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("title")}</h2>
        <p className="text-sm text-text-2">{t("subtitle")}</p>
      </header>

      <div className="space-y-1 rounded border border-border bg-surface p-4">
        <p className="text-sm font-medium text-display-ink">{ticket.event.title}</p>
        <p className="text-xs text-text-2">{startsAt}</p>
      </div>

      {pending ? (
        <div className="space-y-3 rounded border border-border bg-surface p-4">
          <p className="text-sm text-text-2">{t("pendingNotice", { phone: pending.to_phone })}</p>
          <Button
            type="button"
            variant="secondary"
            loading={submitting}
            loadingLabel={t("cancelling")}
            disabled={submitting}
            onClick={() => {
              void handleCancel();
            }}
          >
            {t("cancelCta")}
          </Button>
        </div>
      ) : transferable ? (
        <div className="space-y-3 rounded border border-border bg-surface p-4">
          <FormField id="transfer-phone" label={t("phoneLabel")}>
            <Input
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder={t("phonePlaceholder")}
              type="tel"
              inputMode="tel"
            />
          </FormField>
          <p className="text-xs text-text-2">{t("cutoffNotice")}</p>
          <Button
            type="button"
            variant="primary"
            className="w-full"
            loading={submitting}
            loadingLabel={t("submitting")}
            disabled={!phone.trim() || submitting}
            onClick={() => {
              void handleSubmit();
            }}
          >
            {t("submitCta")}
          </Button>
        </div>
      ) : (
        <p className="text-sm text-text-2">{t("errors.notTransferable")}</p>
      )}

      {message ? <p className="text-center text-sm text-success">{message}</p> : null}
      {error ? <p className="text-center text-sm text-danger">{error}</p> : null}
    </section>
  );
}
