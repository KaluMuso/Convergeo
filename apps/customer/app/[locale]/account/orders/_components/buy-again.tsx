"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

export type BuyAgainLabels = {
  button: string;
  loading: string;
  error: string;
  rateLimited: string;
  /** Template with {count}. */
  added: string;
  nothingAdded: string;
  skippedTitle: string;
  skippedReasons: {
    unavailable: string;
    out_of_stock: string;
    variant_unavailable: string;
  };
  priceChangeTitle: string;
  /** Template with {title}, {previous}, {current}. */
  priceChangeLine: string;
  goToCart: string;
};

export type ReorderResult = {
  order_id: string;
  added: Array<{
    listing_id: string;
    title: string;
    qty: number;
    unit_price_ngwee: number;
  }>;
  skipped: Array<{
    listing_id: string;
    title: string;
    reason: keyof BuyAgainLabels["skippedReasons"];
  }>;
  price_changes: Array<{
    listing_id: string;
    title: string;
    previous_unit_price_ngwee: number;
    current_unit_price_ngwee: number;
  }>;
};

type BuyAgainProps = {
  orderId: string;
  accessToken: string;
  locale: string;
  status: string;
  labels: BuyAgainLabels;
};

const BUY_AGAIN_STATUSES = new Set(["delivered", "completed"]);

export function canBuyAgain(status: string): boolean {
  return BUY_AGAIN_STATUSES.has(status);
}

/**
 * "Buy again": the server re-adds this order's lines through the normal atomic cart
 * path at CURRENT price and stock. We then show what was added, what was skipped and
 * any price movement, so nothing changes silently before checkout.
 */
export function BuyAgain({ orderId, accessToken, locale, status, labels }: BuyAgainProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [result, setResult] = useState<ReorderResult | undefined>();
  // One key per mount: a double-tap or network retry replays instead of doubling qty.
  const idempotencyKey = useRef<string>("");

  const handleClick = useCallback(async () => {
    if (submitting) {
      return;
    }
    if (!idempotencyKey.current) {
      idempotencyKey.current = globalThis.crypto.randomUUID();
    }
    setSubmitting(true);
    setError(undefined);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      setResult(
        await client.request<ReorderResult>(`/cart/reorder/${orderId}`, {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey.current },
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 429 ? labels.rateLimited : labels.error,
      );
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, labels.error, labels.rateLimited, orderId, submitting]);

  if (!canBuyAgain(status)) {
    return null;
  }

  const amountLocale = `${locale}-ZM`;

  if (result) {
    return (
      <div className="space-y-3" role="status" data-testid="buy-again-result">
        <p className="text-sm font-medium text-display-ink">
          {result.added.length > 0
            ? labels.added.replace("{count}", String(result.added.length))
            : labels.nothingAdded}
        </p>
        {result.price_changes.length > 0 ? (
          <div className="space-y-1" data-testid="buy-again-price-changes">
            <p className="text-sm font-medium text-warning">{labels.priceChangeTitle}</p>
            <ul className="space-y-1 text-sm text-text-2">
              {result.price_changes.map((change) => (
                <li key={change.listing_id}>
                  {labels.priceChangeLine
                    .replace("{title}", change.title)
                    .replace(
                      "{previous}",
                      formatK(change.previous_unit_price_ngwee, {
                        locale: amountLocale,
                      }),
                    )
                    .replace(
                      "{current}",
                      formatK(change.current_unit_price_ngwee, {
                        locale: amountLocale,
                      }),
                    )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {result.skipped.length > 0 ? (
          <div className="space-y-1" data-testid="buy-again-skipped">
            <p className="text-sm font-medium text-display-ink">{labels.skippedTitle}</p>
            <ul className="space-y-1 text-sm text-text-2">
              {result.skipped.map((line) => (
                <li key={line.listing_id}>
                  {line.title} — {labels.skippedReasons[line.reason]}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {result.added.length > 0 ? (
          <Link
            href={`/${locale}/cart`}
            className="inline-flex min-h-11 w-full items-center justify-center rounded border border-primary px-4 text-sm font-medium text-primary"
            data-testid="buy-again-go-to-cart"
          >
            {labels.goToCart}
          </Link>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}
      <Button
        type="button"
        variant="secondary"
        className="min-h-11 w-full border-primary px-4 text-sm text-primary"
        loading={submitting}
        loadingLabel={labels.loading}
        onClick={() => void handleClick()}
        data-testid="buy-again-button"
      >
        {labels.button}
      </Button>
    </div>
  );
}
