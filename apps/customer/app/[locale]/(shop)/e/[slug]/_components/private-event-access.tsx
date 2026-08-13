"use client";

import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

type PrivateEventAccessProps = {
  slug: string;
};

/**
 * Unlock is intentionally a same-origin mutation: the access code never enters
 * an event URL, browser history, analytics query string, or the public API log.
 */
export function PrivateEventAccess({ slug }: PrivateEventAccessProps) {
  const t = useTranslations("events.access");
  const router = useRouter();
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!code.trim() || submitting) {
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`/api/events/${encodeURIComponent(slug)}/access`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code.trim() }),
      });
      if (!response.ok) {
        setError(t("errors.invalid"));
        return;
      }
      setCode("");
      router.refresh();
    } catch {
      setError(t("errors.network"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-[55vh] w-full max-w-md items-center px-4 py-12">
      <section className="w-full rounded-lg border border-border bg-surface p-6 shadow-2">
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="mt-2 text-sm leading-relaxed text-text-2">{t("intro")}</p>
        <form className="mt-5 flex flex-col gap-3" onSubmit={unlock}>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-text">
            {t("codeLabel")}
            <input
              autoComplete="one-time-code"
              className="min-h-11 rounded-md border border-border bg-bg px-3 text-text"
              disabled={submitting}
              maxLength={128}
              name="access-code"
              onChange={(event) => setCode(event.target.value)}
              required
              value={code}
            />
          </label>
          {error ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
          <Button
            type="submit"
            disabled={submitting || !code.trim()}
            loading={submitting}
            loadingLabel={t("verifying")}
          >
            {t("continue")}
          </Button>
        </form>
      </section>
    </main>
  );
}
