"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

type InboundTransfer = {
  id: string;
  ticket_id: string;
  expires_at: string;
  event_title: string | null;
  event_venue: string | null;
  starts_at: string | null;
};

/**
 * Standalone inbound-transfer claim banner (M10-P07). Self-fetches
 * `/tickets/transfers/inbound` for the signed-in user's verified phone and
 * lets them claim a pending transfer. Mounted in `tickets/page.tsx` (wrapped
 * in a NextIntlClientProvider) above both the wallet list and the empty
 * state, so a recipient claiming their first ticket still sees it.
 */
export function TicketTransferClaimBanner() {
  const t = useTranslations("events.transfer.claimBanner");
  const tErrors = useTranslations("events.transfer.errors");
  const locale = useLocale();
  const { session, loading: sessionLoading } = useSession();
  const [transfers, setTransfers] = useState<InboundTransfer[]>([]);
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [claimedTicketId, setClaimedTicketId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const client = useMemo(() => createApiClient({ baseUrl: getApiBaseUrl(), getToken }), [getToken]);

  const load = useCallback(async () => {
    try {
      const response = await client.request<{ transfers: InboundTransfer[] }>(
        "/tickets/transfers/inbound",
      );
      setTransfers(response.transfers);
    } catch {
      // Silent — the banner simply stays hidden if the inbound lookup fails.
    }
  }, [client]);

  useEffect(() => {
    if (sessionLoading || !session) {
      return;
    }
    void load();
  }, [sessionLoading, session, load]);

  const handleClaim = useCallback(
    async (transferId: string) => {
      setClaimingId(transferId);
      setError(null);
      try {
        const result = await client.request<{ ticket_id: string }>(
          `/tickets/transfers/${transferId}/claim`,
          { method: "POST" },
        );
        setClaimedTicketId(result.ticket_id);
        setTransfers((prev) => prev.filter((item) => item.id !== transferId));
      } catch (err) {
        if (err instanceof ApiError) {
          switch (err.code) {
            case "forbidden":
              setError(tErrors("phoneMismatch"));
              break;
            case "ticket_transfer_not_pending":
              setError(tErrors("notPending"));
              break;
            case "ticket_transfer_expired":
              setError(tErrors("expired"));
              break;
            case "ticket_not_transferable":
              setError(tErrors("notTransferable"));
              break;
            default:
              setError(err.message || tErrors("generic"));
          }
        } else {
          setError(tErrors("generic"));
        }
      } finally {
        setClaimingId(null);
      }
    },
    [client, tErrors],
  );

  const visible = transfers.filter((item) => !dismissed.has(item.id));

  if (!session || (visible.length === 0 && !claimedTicketId)) {
    return null;
  }

  return (
    <div className="space-y-3">
      {visible.map((transfer) => (
        <div
          key={transfer.id}
          role="status"
          className="space-y-2 rounded border border-primary/30 bg-primary/5 p-4"
        >
          <p className="text-sm font-semibold text-display-ink">{t("title")}</p>
          <p className="text-sm text-text-2">
            {t("body", {
              event: transfer.event_title ?? "",
              datetime: transfer.starts_at
                ? new Date(transfer.starts_at).toLocaleString(locale, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })
                : "",
            })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="primary"
              loading={claimingId === transfer.id}
              loadingLabel={t("claiming")}
              disabled={claimingId !== null}
              onClick={() => {
                void handleClaim(transfer.id);
              }}
            >
              {t("claimCta")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              loadingLabel={t("dismiss")}
              disabled={claimingId !== null}
              onClick={() => setDismissed((prev) => new Set(prev).add(transfer.id))}
            >
              {t("dismiss")}
            </Button>
          </div>
        </div>
      ))}

      {claimedTicketId ? (
        <p className="rounded border border-success/30 bg-success/5 p-4 text-sm text-success">
          {t("claimedNotice")}{" "}
          <Link
            href={`/${locale}/account/tickets/${claimedTicketId}`}
            className="font-semibold underline"
          >
            {t("claimCta")}
          </Link>
        </p>
      ) : null}

      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </div>
  );
}
