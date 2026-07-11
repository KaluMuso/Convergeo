"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { CitationCard } from "./citation-card";
import { QuotaBanner } from "./quota-banner";
import { extractErrorState, relativeAiKey, type AskErrorState, type AskResponse } from "./types";

type AskStatus = "idle" | "loading" | "answered" | "error";

type AskThreadProps = {
  locale: string;
  initialQuery: string;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function AskThread({ locale, initialQuery }: AskThreadProps) {
  const t = useTranslations("ai");
  const { session } = useSession();

  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState<AskStatus>("idle");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [errorState, setErrorState] = useState<AskErrorState | null>(null);
  const autoAskedRef = useRef(false);

  const runAsk = useCallback(
    async (rawQuery: string) => {
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

      try {
        const response = await client.request<AskResponse>("/ask", {
          method: "POST",
          body: JSON.stringify({ query: trimmed }),
        });
        setAnswer(response);
        setStatus("answered");
      } catch (error) {
        setErrorState(extractErrorState(error));
        setStatus("error");
      }
    },
    [session?.access_token],
  );

  // Auto-run the seeded `?q=` query once (deep-link from nav / search zero-results).
  useEffect(() => {
    if (autoAskedRef.current || !initialQuery.trim()) {
      return;
    }
    autoAskedRef.current = true;
    void runAsk(initialQuery);
  }, [initialQuery, runAsk]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runAsk(query);
  };

  const refused = answer?.refused ?? false;
  const showCards = status === "answered" && !refused && (answer?.citations.length ?? 0) > 0;

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
        <Button
          type="submit"
          className="min-h-11 w-full"
          disabled={status === "loading" || !query.trim()}
          loading={status === "loading"}
          loadingLabel={t("ask.submitting")}
        >
          {status === "loading" ? t("ask.submitting") : t("ask.submit")}
        </Button>
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
                    href: `/${locale}/login?next=/${locale}/ask`,
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
            <article className="space-y-3" data-testid="ask-answer">
              <p className="whitespace-pre-wrap text-sm text-text">{answer.answer}</p>

              {showCards ? (
                <section aria-labelledby="ask-citations-title" className="space-y-2">
                  <h2 id="ask-citations-title" className="text-sm font-semibold text-text">
                    {t("ask.citationsTitle")}
                  </h2>
                  <ul className="grid grid-cols-1 gap-2">
                    {answer.citations.map((citation) => (
                      <li key={`${citation.entity_kind}:${citation.entity_id}`}>
                        <CitationCard
                          citation={citation}
                          locale={locale}
                          viewLabel={
                            citation.entity_kind === "event"
                              ? t("ask.viewEvent")
                              : t("ask.viewProduct")
                          }
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <p className="text-xs text-text-3">{t("disclaimer")}</p>
            </article>
          )
        ) : null}
      </div>
    </div>
  );
}
