"use client";

import { useReportClientError } from "@vergeo/observability";
import { useMemo } from "react";

import { getApiBaseUrl } from "../lib/api-base-url";
import { resolveErrorPageCopy, resolveLocaleFromPathname } from "../lib/error-page-copy";

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
  const copy = resolveErrorPageCopy(locale);

  useReportClientError(
    error,
    {
      boundary: "global",
      application: "vendor",
    },
    {
      apiBaseUrl: getApiBaseUrl(),
      locale,
    },
  );

  return (
    <html lang={locale}>
      <body className="bg-surface font-sans text-text antialiased">
        <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-4">
          <p aria-hidden="true" className="font-mono text-4xl font-bold text-primary">
            {copy.code}
          </p>
          <h1 className="text-lg font-semibold text-text">{copy.heading}</h1>
          <p className="text-sm text-text-2">{copy.body}</p>
          <button
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-surface px-4 text-sm font-medium text-text"
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
