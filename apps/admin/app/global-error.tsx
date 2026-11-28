"use client";

import { useReportClientError } from "@vergeo/observability";
import { useEffect, useMemo } from "react";

import { getApiBaseUrl } from "../lib/api-base-url";
import { reloadOnceForChunkError } from "../lib/chunk-reload";
import { resolveErrorPageCopy, resolveLocaleFromPathname } from "../lib/error-page-copy";

import "./globals.css";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

/** Last-resort boundary for failures in the root/locale layout (replaces the whole document). */
export default function GlobalError({ error, reset }: GlobalErrorProps) {
  const locale = useMemo(
    () =>
      typeof window === "undefined" ? "en" : resolveLocaleFromPathname(window.location.pathname),
    [],
  );
  const copy = resolveErrorPageCopy(locale);

  useEffect(() => {
    reloadOnceForChunkError(error);
  }, [error]);

  useReportClientError(
    error,
    { boundary: "global", application: "admin" },
    { apiBaseUrl: getApiBaseUrl(), locale },
  );

  return (
    <html lang={locale}>
      <body className="bg-surface font-sans text-text antialiased">
        <main
          role="alert"
          className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-6"
          data-testid="admin-global-error"
        >
          <h1 className="text-lg font-semibold">{copy.heading}</h1>
          <p className="text-sm text-muted">{copy.body}</p>
          <button
            className="inline-flex min-h-11 items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
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
