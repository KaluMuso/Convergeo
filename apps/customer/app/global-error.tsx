"use client";

import { useReportClientError } from "@vergeo/observability";
import { useMemo } from "react";

import { getApiBaseUrl } from "../lib/api-base-url";
import { resolveLocaleFromPathname, resolveMarketingErrorCopy } from "../lib/marketing-error-copy";

import "./globals.css";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  const locale = useMemo(
    () =>
      typeof window === "undefined" ? "en" : resolveLocaleFromPathname(window.location.pathname),
    [],
  );
  const copy = resolveMarketingErrorCopy(locale);

  useReportClientError(
    error,
    {
      boundary: "global",
      application: "customer",
    },
    {
      apiBaseUrl: getApiBaseUrl(),
      locale,
    },
  );

  return (
    <html lang={locale}>
      <body className="bg-surface font-sans text-text antialiased">
        <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-6">
          <p aria-hidden="true" className="font-mono text-5xl font-bold text-primary">
            {copy.code}
          </p>
          <h1 className="font-display text-h1 text-display-ink">{copy.heading}</h1>
          <p className="text-body text-text-2">{copy.body}</p>
          <button
            className="mt-2 inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
            onClick={reset}
            type="button"
          >
            {copy.retry}
          </button>
        </main>
      </body>
    </html>
  );
}
