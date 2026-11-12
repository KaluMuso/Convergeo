"use client";

import { createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { useSession } from "../../../../../lib/customer-session";

import { CitationCard } from "./citation-card";
import { FaqList } from "./faq-list";
import { QuotaBanner } from "./quota-banner";
import { QuotaMeter } from "./quota-meter";
import {
  extractErrorState,
  parseQuota,
  relativeAiKey,
  type AskCitation,
  type AskErrorState,
  type AskQuota,
  type AskResponse,
} from "./types";
import { AskVoiceButton } from "./voice-button";

type AskStatus = "idle" | "loading" | "answered" | "error";

type AskThreadProps = {
  locale: string;
  initialQuery: string;
};

type Coords = { lat: number; lng: number };

/** ~100 m precision is plenty for "near me" and avoids sending exact positions. */
function roundCoord(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function viewLabelKey(kind: string): string {
  switch (kind) {
    case "event":
      return "ask.viewEvent";
    case "vendor":
      return "ask.viewVendor";
    case "service":
      return "ask.viewService";
    default:
      return "ask.viewProduct";
  }
}

export function AskThread({ locale, initialQuery }: AskThreadProps) {
  const t = useTranslations("ai");
  const { session } = useSession();

  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState<AskStatus>("idle");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [errorState, setErrorState] = useState<AskErrorState | null>(null);
  const [quota, setQuota] = useState<AskQuota | null>(null);
  const [locationDenied, setLocationDenied] = useState(false);
  const lastAutoAskedRef = useRef<string | null>(null);

  const runAsk = useCallback(
    async (rawQuery: string, coords?: Coords) => {
      const trimmed = rawQuery.trim();
      if (!trimmed) {
        return;
      }

      setStatus("loading");
      setAnswer(null);
      setErrorState(null);

      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => session?.access_token ?? null,
      });

      const payload: { query: string; lat?: number; lng?: number } = { query: trimmed };
      if (coords) {
        payload.lat = roundCoord(coords.lat);
        payload.lng = roundCoord(coords.lng);
      }

      try {
        const response = await client.request<AskResponse>("/ask", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setAnswer(response);
        const nextQuota = parseQuota(response?.quota);
        if (nextQuota) {
          setQuota(nextQuota);
        }
        setStatus("answered");
      } catch (error) {
        setErrorState(extractErrorState(error));
        setStatus("error");
      }
    },
    [session?.access_token],
  );

  // Auto-run a seeded `?q=` query (deep-link from nav / search zero-results / voice FAB).
  useEffect(() => {
    const seeded = initialQuery.trim();
    if (!seeded || lastAutoAskedRef.current === seeded) {
      return;
    }
    lastAutoAskedRef.current = seeded;
    setQuery(seeded);
    void runAsk(seeded);
  }, [initialQuery, runAsk]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runAsk(query);
  };

  const handleTranscript = useCallback(
    (text: string, isFinal: boolean) => {
      setQuery(text);
      if (isFinal) {
        void runAsk(text);
      }
    },
    [runAsk],
  );

  const handleUseLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation || !answer) {
      setLocationDenied(true);
      return;
    }
    const askedQuery = answer.query;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocationDenied(false);
        void runAsk(askedQuery, {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
      },
      () => setLocationDenied(true),
      { enableHighAccuracy: false, maximumAge: 300_000, timeout: 10_000 },
    );
  };

  const source = answer?.source ?? "ai";
  const refused = answer?.refused ?? false;
  const citations = answer?.citations ?? [];
  const faqItems = (answer?.faq ?? []).map((item) => ({
    id: item.id,
    question: t(relativeAiKey(item.question_key)),
    answer: t(relativeAiKey(item.answer_key)),
  }));
  const orders = answer?.orders ?? [];

  const citationMeta = (citation: AskCitation): string | null => {
    if (typeof citation.distance_km === "number") {
      return t("ask.distance", { km: citation.distance_km.toFixed(1) });
    }
    if (citation.in_stock === false) {
      return t("ask.outOfStock");
    }
    if (citation.in_stock === true) {
      return t("ask.inStock");
    }
    return null;
  };

  const answerText = (): string | null => {
    if (!answer) {
      return null;
    }
    if (answer.answer_key) {
      return t(relativeAiKey(answer.answer_key), answer.answer_params ?? {});
    }
    if (source === "fallback") {
      return null;
    }
    return answer.answer;
  };

  const loginHref = `/${locale}/login?next=/${locale}/ask`;
  const text = status === "answered" ? answerText() : null;

  return (
    <div className="mx-auto flex w-full max-w-[360px] flex-col gap-4">
      <header className="space-y-1">
        <h1 className="font-display text-h1 text-display-ink">{t("ask.title")}</h1>
        <p className="text-sm text-text-2">{t("ask.subtitle")}</p>
      </header>

      <form className="flex flex-col gap-2" onSubmit={handleSubmit}>
        <label htmlFor="ask-input" className="sr-only">
          {t("ask.inputLabel")}
        </label>
        <div className="flex items-start gap-2">
          <textarea
            id="ask-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("ask.inputPlaceholder")}
            aria-label={t("ask.inputLabel")}
            rows={2}
            maxLength={500}
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text"
          />
          <AskVoiceButton
            disabled={status === "loading"}
            onTranscript={handleTranscript}
            labels={{
              start: t("ask.voiceStart"),
              stop: t("ask.voiceStop"),
              listening: t("ask.voiceListening"),
              error: t("ask.voiceError"),
            }}
          />
        </div>
        <Button
          type="submit"
          className="min-h-11 w-full"
          disabled={status === "loading" || !query.trim()}
          loading={status === "loading"}
          loadingLabel={t("ask.submitting")}
        >
          {status === "loading" ? t("ask.submitting") : t("ask.submit")}
        </Button>
        {quota ? (
          <QuotaMeter
            quota={quota}
            label={t("quota.remainingToday", { count: quota.remaining })}
            premiumLabel={t("quota.premiumBadge")}
          />
        ) : null}
      </form>

      <div aria-live="polite" className="space-y-4">
        {status === "idle" ? <p className="text-sm text-text-3">{t("ask.emptyHint")}</p> : null}

        {status === "loading" ? (
          <p className="text-sm text-text-3" data-testid="ask-loading">
            {t("ask.submitting")}
          </p>
        ) : null}

        {status === "error" && errorState ? (
          <QuotaBanner
            message={t(relativeAiKey(errorState.messageKey))}
            signup={
              errorState.signupPromptKey
                ? {
                    prompt: t(relativeAiKey(errorState.signupPromptKey)),
                    ctaLabel: t("ask.signupCta"),
                    href: loginHref,
                  }
                : null
            }
          />
        ) : null}

        {status === "answered" && answer ? (
          refused ? (
            <p className="text-sm text-text-2" data-testid="ask-refusal">
              {t(relativeAiKey(answer.message_key ?? "ai.answer.not_found"))}
            </p>
          ) : (
            <article className="space-y-3" data-testid="ask-answer" data-source={source}>
              {answer.notice_key ? (
                <QuotaBanner
                  message={t(relativeAiKey(answer.notice_key))}
                  signup={
                    answer.signup_prompt_key
                      ? {
                          prompt: t(relativeAiKey(answer.signup_prompt_key)),
                          ctaLabel: t("ask.signupCta"),
                          href: loginHref,
                        }
                      : null
                  }
                />
              ) : null}

              {text ? <p className="whitespace-pre-wrap text-sm text-text">{text}</p> : null}

              {answer.sign_in_required ? (
                <Link
                  href={loginHref}
                  data-testid="ask-signin-cta"
                  className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline underline-offset-2"
                >
                  {t("ask.signInCta")}
                </Link>
              ) : null}

              {answer.needs_location ? (
                <div className="space-y-1">
                  <Button
                    type="button"
                    variant="secondary"
                    className="min-h-11"
                    onClick={handleUseLocation}
                    loadingLabel={t("ask.submitting")}
                    data-testid="ask-use-location"
                  >
                    {t("ask.useLocation")}
                  </Button>
                  {locationDenied ? (
                    <p className="text-xs text-text-3">{t("ask.locationDenied")}</p>
                  ) : null}
                </div>
              ) : null}

              {orders.length > 0 ? (
                <section aria-labelledby="ask-orders-title" className="space-y-2">
                  <h2 id="ask-orders-title" className="text-sm font-semibold text-text">
                    {t("ask.ordersTitle")}
                  </h2>
                  <ul className="grid grid-cols-1 gap-2">
                    {orders.map((order) => (
                      <li key={order.id}>
                        <Link
                          href={`/${locale}/account/orders/${encodeURIComponent(order.id)}`}
                          aria-label={`${t("ask.viewOrder")}: ${t("ask.orderRef", { ref: order.ref })}`}
                          data-testid="ask-order-card"
                          className="flex min-h-16 flex-col justify-center gap-1 rounded-lg border border-border bg-surface p-3 hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
                        >
                          <span className="text-sm font-medium text-text">
                            {t("ask.orderRef", { ref: order.ref })}
                          </span>
                          <span className="text-sm text-text-2">
                            {t(relativeAiKey(order.status_key))}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {citations.length > 0 ? (
                <section aria-labelledby="ask-citations-title" className="space-y-2">
                  <h2 id="ask-citations-title" className="text-sm font-semibold text-text">
                    {source === "fallback" ? t("fallback.resultsTitle") : t("ask.citationsTitle")}
                  </h2>
                  <ul className="grid grid-cols-1 gap-2">
                    {citations.map((citation) => (
                      <li key={`${citation.entity_kind}:${citation.entity_id}`}>
                        <CitationCard
                          citation={citation}
                          locale={locale}
                          viewLabel={t(viewLabelKey(citation.entity_kind))}
                          meta={citationMeta(citation)}
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <FaqList title={t("ask.faqTitle")} items={faqItems} />

              {source === "ai" ? <p className="text-xs text-text-3">{t("disclaimer")}</p> : null}
            </article>
          )
        ) : null}
      </div>
    </div>
  );
}
