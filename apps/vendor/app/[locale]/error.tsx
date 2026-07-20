"use client";

import { useTranslations } from "next-intl";

type ErrorProps = {
  reset: () => void;
};

export default function ErrorBoundary({ reset }: ErrorProps) {
  const t = useTranslations("common");

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-4">
      <h1 className="text-lg font-semibold">{t("app.name")}</h1>
      <p className="text-sm text-text-2">{t("common.retry")}</p>
      <button
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-surface px-4 text-sm font-medium text-text"
        onClick={reset}
        type="button"
      >
        {t("common.retry")}
      </button>
    </main>
  );
}
