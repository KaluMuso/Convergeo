"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Button, Spinner } from "../../listings/new/_lib/ui";

type MarkCompleteResponse = {
  job_id: string;
  order_id: string;
  marked: boolean;
};

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export default function VendorJobCompletePage({ params }: PageProps) {
  const t = useTranslations("services.completion.provider");
  const { session, loading: sessionLoading } = useSession();
  const [locale, setLocale] = useState("en");
  const [jobId, setJobId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [marked, setMarked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void params.then(({ locale: nextLocale, id }) => {
      setLocale(nextLocale);
      setJobId(id);
    });
  }, [params]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const handleMarkComplete = useCallback(async () => {
    if (!jobId) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
      const result = await client.request<MarkCompleteResponse>(`/jobs/${jobId}/complete`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMarked(true);
      void result;
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("errors.notProvider"));
      } else if (err instanceof ApiError && err.status === 404) {
        setError(t("errors.notFound"));
      } else if (err instanceof ApiError && err.status === 429) {
        setError(t("errors.rateLimited"));
      } else {
        setError(t("errors.generic"));
      }
      setSubmitting(false);
    }
  }, [getToken, jobId, t]);

  if (sessionLoading) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
        <div className="flex min-h-[40vh] items-center justify-center">
          <Spinner label={t("marking")} />
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col gap-4 p-4">
      <header className="space-y-1">
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      <section className="space-y-4 rounded border border-border bg-surface p-4">
        {marked ? (
          <p className="text-sm font-medium text-success">{t("marked")}</p>
        ) : (
          <>
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            <Button
              type="button"
              variant="primary"
              loading={submitting}
              loadingLabel={t("marking")}
              disabled={submitting}
              onClick={() => void handleMarkComplete()}
            >
              {t("markCta")}
            </Button>
          </>
        )}
        <Link href={`/${locale}/jobs`} className="block text-center text-sm text-text-2 underline">
          {t("backToJobs")}
        </Link>
      </section>
    </main>
  );
}
