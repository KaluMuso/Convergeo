"use client";

import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

export function EventTeamAcceptForm() {
  const t = useTranslations("events.teamAccept");
  const searchParams = useSearchParams();
  const initialToken = searchParams.get("token") ?? "";
  const [token, setToken] = useState(initialToken);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const onSubmit = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const { createBrowserClient } = await import("@vergeo/auth");
      const supabase = createBrowserClient();
      const { data } = await supabase.auth.getSession();
      const access = data.session?.access_token;
      if (!access) {
        setError(t("loginRequired"));
        return;
      }
      const response = await fetch(
        `${getApiBaseUrl().replace(/\/$/, "")}/account/event-team/accept`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${access}`,
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ token: token.trim() }),
        },
      );
      if (!response.ok) {
        setError(t("failed"));
        return;
      }
      setDone(true);
    } catch {
      setError(t("failed"));
    } finally {
      setBusy(false);
    }
  }, [t, token]);

  if (done) {
    return <p className="text-sm text-success">{t("success")}</p>;
  }

  return (
    <form
      className="flex max-w-md flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit();
      }}
    >
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium">{t("tokenLabel")}</span>
        <input
          className="min-h-11 rounded-md border border-border bg-bg px-3"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          autoComplete="off"
        />
      </label>
      <button
        type="submit"
        className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] disabled:opacity-50"
        disabled={busy || !token.trim()}
      >
        {busy ? t("submitting") : t("cta")}
      </button>
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
