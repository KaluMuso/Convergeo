"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { OtpField } from "@vergeo/ui/src/otp-field";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { clearUserCaches } from "../../../../lib/clear-user-caches";
import {
  type DeliveryConsent,
  isConsentCurrent,
  loadDeliveryConsent,
  saveDeliveryConsent,
} from "../../../../lib/delivery-consent";

const API_BASE_URL = getApiBaseUrl();
const DELETE_CONFIRMATION_PHRASE = "DELETE MY ACCOUNT";

type ExportResponse = {
  export_id: string;
  download_url: string;
  expires_in_seconds: number;
};

export default function AccountPrivacyPage() {
  const params = useParams<{ locale: string }>();
  const locale = params.locale;

  useEffect(() => {
    const existing = document.querySelector('meta[name="robots"]');
    if (existing) {
      existing.setAttribute("content", "noindex, nofollow");
      return;
    }
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow";
    document.head.appendChild(meta);
  }, []);

  return (
    <div className="flex w-full max-w-lg flex-col gap-8">
      <PrivacyIntro locale={locale} />
      <DeliveryConsentSection locale={locale} />
      <ExportSection locale={locale} />
      <DeleteSection locale={locale} />
    </div>
  );
}

function PrivacyIntro({ locale }: { locale: string }) {
  const t = useTranslations("account.privacy");

  return (
    <>
      <header className="space-y-2">
        <p className="text-sm text-muted">
          <Link className="underline underline-offset-2" href={`/${locale}/account`}>
            {t("backToAccount")}
          </Link>
        </p>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm leading-relaxed text-muted">{t("description")}</p>
      </header>
      <p className="rounded-lg border border-border bg-bg-2/60 px-4 py-3 text-sm leading-relaxed text-muted">
        {t("retentionNote")}
      </p>
    </>
  );
}

function DeliveryConsentSection({ locale }: { locale: string }) {
  const t = useTranslations("account.privacy.deliveryConsent");
  const [consent, setConsent] = useState<DeliveryConsent | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadDeliveryConsent().then(
      (value) => {
        if (active) {
          setConsent(value);
          setLoaded(true);
        }
      },
      () => {
        if (active) {
          setError(t("loadFailed"));
          setLoaded(true);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [t]);

  const granted = isConsentCurrent(consent);

  const toggle = async (next: boolean) => {
    setSaving(true);
    setError(null);
    try {
      setConsent(await saveDeliveryConsent(next, "settings"));
    } catch {
      setError(t("saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      aria-labelledby="delivery-consent-heading"
      className="space-y-3 rounded-xl border border-border p-4"
    >
      <h2 id="delivery-consent-heading" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-sm leading-relaxed text-muted">{t("description")}</p>
      <label className="flex min-h-11 items-start gap-3 text-sm">
        <input
          type="checkbox"
          className="mt-1 h-5 w-5"
          checked={granted}
          disabled={!loaded || saving}
          onChange={(event) => void toggle(event.target.checked)}
          data-testid="delivery-consent-toggle"
        />
        <span>{t("label")}</span>
      </label>
      <p className="text-xs text-muted" role="status">
        {!loaded
          ? t("loading")
          : granted && consent?.recorded_at
            ? t("grantedAt", {
                at: new Date(consent.recorded_at).toLocaleDateString(`${locale}-ZM`),
              })
            : t("notGranted")}
      </p>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </section>
  );
}

function ExportSection({ locale }: { locale: string }) {
  const t = useTranslations("account.privacy.export");
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const api = useMemo(
    () =>
      createApiClient({
        baseUrl: API_BASE_URL,
        getToken: async () => {
          const supabase = await getBrowserClient();
          const { data } = await supabase.auth.getSession();
          return data.session?.access_token ?? null;
        },
      }),
    [],
  );

  const handleExport = async () => {
    setLoading(true);
    setError(null);
    setDownloadUrl(null);
    try {
      const result = await api.request<ExportResponse>("/account/export", {
        method: "POST",
      });
      setDownloadUrl(result.download_url);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section
      aria-labelledby="export-heading"
      className="space-y-3 rounded-xl border border-border p-4"
    >
      <h2 id="export-heading" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-sm leading-relaxed text-muted">{t("description")}</p>
      <Button
        className="min-h-11 w-full"
        loading={loading}
        loadingLabel={t("loading")}
        onClick={handleExport}
        type="button"
      >
        {t("button")}
      </Button>
      {downloadUrl ? (
        <p className="text-sm text-primary">
          <a
            className="font-medium underline underline-offset-2"
            href={downloadUrl}
            rel="noreferrer"
          >
            {t("success")}
          </a>
        </p>
      ) : null}
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <p className="text-xs text-muted">
        <Link className="underline underline-offset-2" href={`/${locale}/legal/privacy`}>
          {t("policyLink")}
        </Link>
      </p>
    </section>
  );
}

function DeleteSection({ locale }: { locale: string }) {
  const t = useTranslations("account.privacy.delete");
  const [phrase, setPhrase] = useState("");
  const [otp, setOtp] = useState("");
  const [phone, setPhone] = useState<string | null>(null);
  const [otpSent, setOtpSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [otpLoading, setOtpLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const api = useMemo(
    () =>
      createApiClient({
        baseUrl: API_BASE_URL,
        getToken: async () => {
          const supabase = await getBrowserClient();
          const { data } = await supabase.auth.getSession();
          return data.session?.access_token ?? null;
        },
      }),
    [],
  );

  useEffect(() => {
    const loadPhone = async () => {
      const supabase = await getBrowserClient();
      const { data } = await supabase.auth.getUser();
      const userPhone = data.user?.phone;
      setPhone(typeof userPhone === "string" ? userPhone : null);
    };
    void loadPhone();
  }, []);

  const handleSendOtp = async () => {
    if (!phone) {
      setError(t("phoneRequired"));
      return;
    }
    setOtpLoading(true);
    setError(null);
    try {
      const supabase = await getBrowserClient();
      const { error: otpError } = await supabase.auth.signInWithOtp({ phone });
      if (otpError) {
        setError(t("otpSendFailed"));
        return;
      }
      setOtpSent(true);
    } catch {
      setError(t("otpSendFailed"));
    } finally {
      setOtpLoading(false);
    }
  };

  const handleDelete = async () => {
    if (phrase.trim() !== DELETE_CONFIRMATION_PHRASE || otp.length !== 6) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.request("/account/delete", {
        method: "POST",
        body: JSON.stringify({ confirmation_phrase: phrase.trim(), otp }),
      });
      setDone(true);
      const supabase = await getBrowserClient();
      await supabase.auth.signOut();
      await clearUserCaches();
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  };

  const phraseMatches = phrase.trim() === DELETE_CONFIRMATION_PHRASE;
  const canSubmit = phraseMatches && otp.length === 6 && !loading && !done;

  return (
    <section
      aria-labelledby="delete-heading"
      className="space-y-4 rounded-xl border border-danger/40 p-4"
    >
      <h2 id="delete-heading" className="text-lg font-semibold text-danger">
        {t("title")}
      </h2>
      <p className="text-sm leading-relaxed text-muted">{t("description")}</p>
      <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm leading-relaxed text-danger">
        {t("warning")}
      </p>

      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="delete-phrase">
          {t("confirmPhraseLabel")}
        </label>
        <input
          autoComplete="off"
          className="min-h-11 w-full rounded-md border border-border bg-surface px-3 text-sm"
          id="delete-phrase"
          onChange={(event) => setPhrase(event.target.value)}
          placeholder={t("confirmPhraseHint")}
          type="text"
          value={phrase}
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium">{t("otpLabel")}</span>
          <Button
            className="min-h-11"
            disabled={otpLoading || !phone || done}
            loading={otpLoading}
            loadingLabel={t("otpSending")}
            onClick={handleSendOtp}
            type="button"
            variant="secondary"
          >
            {otpSent ? t("otpResend") : t("sendOtp")}
          </Button>
        </div>
        <OtpField
          ariaLabel={t("otpAria")}
          getDigitAriaLabel={(index) => t("otpDigit", { position: index + 1, total: 6 })}
          onChange={setOtp}
          onComplete={setOtp}
          value={otp}
        />
      </div>

      <Button
        className="min-h-11 w-full"
        disabled={!canSubmit}
        loading={loading}
        loadingLabel={t("loading")}
        onClick={handleDelete}
        type="button"
        variant="destructive"
      >
        {done ? t("success") : t("submit")}
      </Button>

      {done ? (
        <p className="text-sm text-muted">
          <Link className="underline underline-offset-2" href={`/${locale}/login`}>
            {t("returnToLogin")}
          </Link>
        </p>
      ) : null}
      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </section>
  );
}
