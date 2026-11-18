"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import {
  extraPriceLabel,
  openRequestFor,
  type Extra,
  type ExtraRequest,
  type ExtrasCatalogueResponse,
} from "../_lib/extras";

type ApiError = { details?: { message_key?: string } };

function errorKey(error: unknown): string {
  const key = (error as ApiError | null)?.details?.message_key;
  if (key === "vendor.extras.errors.alreadyRequested")
    return "errors.alreadyRequested";
  if (key === "vendor.extras.errors.rateLimited") return "errors.rateLimited";
  if (key === "vendor.extras.errors.notFound") return "errors.notFound";
  return "errors.generic";
}

/**
 * Paid extras: the admin-edited catalogue with a Request button per extra.
 * Payments are off — a request tells our team, who quote or approve it; no
 * money is collected here.
 */
export function ExtrasCatalogue() {
  const t = useTranslations("vendor.extras");
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const client = useMemo(
    () => createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => token }),
    [token],
  );
  const [data, setData] = useState<ExtrasCatalogueResponse | null | "error">(
    null,
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    client
      .request<ExtrasCatalogueResponse>("/vendor/extras")
      .then(setData)
      .catch(() => setData("error"));
  }, [client]);

  useEffect(() => {
    if (token) load();
  }, [load, token]);

  const act = useCallback(
    async (key: string, path: string, body?: unknown) => {
      setBusy(key);
      setMessage(null);
      try {
        await client.request(path, {
          method: "POST",
          body: body ? JSON.stringify(body) : undefined,
        });
        setMessage(t("requested"));
        load();
      } catch (error) {
        setMessage(t(errorKey(error)));
      } finally {
        setBusy(null);
      }
    },
    [client, load, t],
  );

  if (data === null)
    return <p className="text-sm text-text-2">{t("loading")}</p>;
  if (data === "error")
    return <p className="text-sm text-text-2">{t("errors.load")}</p>;

  return (
    <div className="space-y-3">
      <p className="m-0 text-sm text-text-2">{t("noPayment")}</p>
      {message ? (
        <p role="status" className="m-0 text-sm text-text">
          {message}
        </p>
      ) : null}
      <ul className="m-0 list-none space-y-3 p-0" data-testid="extras-list">
        {data.extras.map((extra) => (
          <ExtraCard
            key={extra.key}
            extra={extra}
            request={openRequestFor(data.requests, extra.key)}
            busy={busy === extra.key}
            onRequest={() =>
              void act(extra.key, "/vendor/extras/requests", {
                extra_key: extra.key,
              })
            }
            onAccept={(id) =>
              void act(extra.key, `/vendor/extras/requests/${id}/accept`)
            }
            onCancel={(id) =>
              void act(extra.key, `/vendor/extras/requests/${id}/cancel`)
            }
          />
        ))}
      </ul>
    </div>
  );
}

function ExtraCard({
  extra,
  request,
  busy,
  onRequest,
  onAccept,
  onCancel,
}: {
  extra: Extra;
  request: ExtraRequest | undefined;
  busy: boolean;
  onRequest: () => void;
  onAccept: (id: string) => void;
  onCancel: (id: string) => void;
}) {
  const t = useTranslations("vendor.extras");
  return (
    <li
      className="space-y-2 rounded-lg border border-border bg-surface p-4 shadow-1"
      data-testid={`extra-${extra.key}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="m-0 text-base font-semibold text-text">{extra.name}</h2>
        <span className="text-sm font-medium text-text">
          {extraPriceLabel(extra, t)}
        </span>
      </div>
      {extra.description ? (
        <p className="m-0 text-sm text-text-2">{extra.description}</p>
      ) : null}
      {extra.price_is_placeholder ? (
        <p className="m-0 text-micro text-text-2">{t("indicativePrice")}</p>
      ) : null}
      {request ? (
        <div className="space-y-2">
          <p
            className="m-0 text-sm text-text"
            data-testid={`extra-${extra.key}-status`}
          >
            {request.status === "quoted" && request.quoted_price_ngwee !== null
              ? t("status.quotedWithPrice", {
                  price: formatK(request.quoted_price_ngwee),
                })
              : t(`status.${request.status}`)}
          </p>
          {request.admin_note ? (
            <p className="m-0 text-sm text-text-2">
              {t("teamNote", { note: request.admin_note })}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {request.status === "quoted" ? (
              <Button
                type="button"
                loading={busy}
                loadingLabel={t("actions.working")}
                disabled={busy}
                onClick={() => onAccept(request.id)}
              >
                {t("actions.accept")}
              </Button>
            ) : null}
            {request.status === "requested" || request.status === "quoted" ? (
              <Button
                type="button"
                variant="secondary"
                loadingLabel={t("actions.working")}
                disabled={busy}
                onClick={() => onCancel(request.id)}
              >
                {t("actions.cancel")}
              </Button>
            ) : null}
          </div>
        </div>
      ) : (
        <Button
          type="button"
          loading={busy}
          loadingLabel={t("actions.working")}
          disabled={busy}
          onClick={onRequest}
        >
          {t("actions.request")}
        </Button>
      )}
    </li>
  );
}
