"use client";

import { useReportClientError } from "@vergeo/observability";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";

import { getApiBaseUrl } from "../../../lib/api-base-url";
import { reloadOnceForChunkError } from "../../../lib/chunk-reload";
import { resolveMarketingErrorCopy } from "../../../lib/marketing-error-copy";

type ShopErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

/**
 * Shop-segment error boundary. Unlike the locale-level boundary it sits INSIDE
 * the shop layout, so a failing page keeps the header, search and bottom nav and
 * the shopper can navigate away without a full reload.
 */
export default function ShopError({ error, reset }: ShopErrorProps) {
  const params = useParams();
  const locale = typeof params?.locale === "string" ? params.locale : "en";
  const copy = resolveMarketingErrorCopy(locale);

  useEffect(() => {
    reloadOnceForChunkError(error);
  }, [error]);

  useReportClientError(
    error,
    { boundary: "route", application: "customer" },
    { apiBaseUrl: getApiBaseUrl(), locale },
  );

  return (
    <section
      data-testid="shop-error"
      role="alert"
      className="mx-auto flex min-h-[50dvh] w-full max-w-xl flex-col items-start justify-center gap-3 px-1 py-10"
    >
      <h1 className="m-0 font-display text-h1 font-bold text-display-ink">{copy.heading}</h1>
      <p className="m-0 max-w-prose text-body text-text-2">{copy.body}</p>
      <div className="mt-2 flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-5 text-body font-semibold text-[var(--primary-btn-fg)] hover:bg-[var(--primary-btn-hover)]"
          onClick={reset}
          type="button"
        >
          {copy.retry}
        </button>
        <LinkButton href={`/${locale}`} variant="secondary" LinkComponent={Link}>
          {copy.home}
        </LinkButton>
      </div>
    </section>
  );
}
