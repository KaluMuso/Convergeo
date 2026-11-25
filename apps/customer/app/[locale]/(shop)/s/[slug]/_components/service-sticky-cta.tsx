"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";
import { useSession } from "../../../../../../lib/customer-session";
import { RequestQuoteButton } from "../../../_components/pdp/request-quote-button";

import type { RequestQuoteLabels } from "../../../_components/pdp/request-quote-button";

export type ServiceStickyKind = "free" | "book" | "quote_direct" | "quote_browse";

export type ServiceStickyCtaLabels = {
  ariaLabel: string;
  freeCta: string;
  bookCta: string;
  quoteCta: string;
  freeSubmitting: string;
  bookSubmitting: string;
  errors: {
    authRequired: string;
    generic: string;
  };
};

export type ServiceStickyCtaProps = {
  locale: string;
  serviceId: string;
  vendorName: string;
  observeRef: RefObject<HTMLElement | null>;
  kind: ServiceStickyKind;
  bookingPriceNgwee: number | null;
  quoteHref: string;
  quoteLabels: RequestQuoteLabels;
  priceLine: string;
  labels: ServiceStickyCtaLabels;
};

export function ServiceStickyCta({
  locale,
  serviceId,
  vendorName,
  observeRef,
  kind,
  quoteHref,
  quoteLabels,
  priceLine,
  labels,
}: ServiceStickyCtaProps) {
  const router = useRouter();
  const { session } = useSession();
  const [sidebarOutOfView, setSidebarOutOfView] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const idempotencyKeyRef = useRef<string | null>(null);

  useEffect(() => {
    const target = observeRef.current;
    if (!target || typeof IntersectionObserver === "undefined") {
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry) {
          return;
        }
        setSidebarOutOfView(!entry.isIntersecting);
      },
      { root: null, threshold: 0.1, rootMargin: "0px 0px -72px 0px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [observeRef]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const postStickyAction = useCallback(
    async (path: string) => {
      if (!session) {
        return;
      }
      setSubmitting(true);
      idempotencyKeyRef.current ??= crypto.randomUUID();
      try {
        const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
        const result = await client.request<{ checkout_group_id?: string }>(path, {
          method: "POST",
          body: JSON.stringify({
            idempotency_key: idempotencyKeyRef.current,
          }),
        });
        if (result.checkout_group_id) {
          router.push(
            `/${locale}/checkout?group=${encodeURIComponent(result.checkout_group_id)}&kind=service_deposit`,
          );
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          void err;
        }
      } finally {
        setSubmitting(false);
      }
    },
    [getToken, locale, router, session],
  );

  if (!sidebarOutOfView) {
    return null;
  }

  return (
    <aside
      data-testid="service-sticky-cta"
      aria-label={labels.ariaLabel}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 p-3 shadow-2 backdrop-blur lg:hidden"
    >
      <div className="mx-auto flex w-full max-w-[1400px] items-center gap-3">
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-text">{priceLine}</p>
        <div className="shrink-0">
          {kind === "free" ? (
            <Button
              type="button"
              variant="primary"
              className="min-h-11 rounded-md px-4 text-sm font-semibold"
              loading={submitting}
              loadingLabel={labels.freeSubmitting}
              disabled={!session || submitting}
              onClick={() => void postStickyAction(`/services/${serviceId}/request-free`)}
            >
              {labels.freeCta}
            </Button>
          ) : null}
          {kind === "book" ? (
            <Button
              type="button"
              variant="primary"
              className="min-h-11 rounded-md px-4 text-sm font-semibold"
              loading={submitting}
              loadingLabel={labels.bookSubmitting}
              disabled={!session || submitting}
              onClick={() => void postStickyAction(`/services/${serviceId}/book`)}
            >
              {labels.bookCta}
            </Button>
          ) : null}
          {kind === "quote_direct" ? (
            <RequestQuoteButton
              locale={locale}
              serviceId={serviceId}
              vendorName={vendorName}
              labels={quoteLabels}
              variant="primary"
              className="min-h-11 rounded-md px-4 text-sm font-semibold"
            />
          ) : null}
          {kind === "quote_browse" ? (
            <LinkButton
              href={quoteHref}
              variant="primary"
              className="min-h-11 rounded-md px-4 text-sm font-semibold"
              LinkComponent={Link}
            >
              {labels.quoteCta}
            </LinkButton>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
