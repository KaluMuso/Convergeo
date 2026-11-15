"use client";

import { useSession } from "@vergeo/auth/use-session";
import { LOCALES } from "@vergeo/i18n";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { maskMsisdn, swapLocaleInPath } from "../../../../lib/locale-path";
import { isVendorPayoutsEnabled } from "../../../../lib/payouts-availability";
import { Button, FormField, Select } from "../../listings/new/_lib/ui";
import { createPayoutsClient } from "../../payouts/_lib/payouts-client";

import type { PayoutBalances } from "../../payouts/_lib/payouts-client";

type Props = { locale: string };

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-labelledby={`settings-${id}`}
      data-testid={`settings-${id}`}
      className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-4"
    >
      <h2
        id={`settings-${id}`}
        className="text-sm font-semibold uppercase tracking-wide text-text-3"
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

/**
 * Vendor settings hub: account, notifications, payout method (view only) and
 * language. Each section links out to the page that owns the editing flow.
 */
export function SettingsView({ locale }: Props) {
  const t = useTranslations("vendor");
  const pathname = usePathname();
  const router = useRouter();
  const { session, user } = useSession();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutFailed, setSignOutFailed] = useState(false);
  const [balances, setBalances] = useState<PayoutBalances | null>(null);
  const [payoutState, setPayoutState] = useState<"idle" | "loading" | "failed">("idle");
  const payoutsLive = isVendorPayoutsEnabled();

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const payoutsClient = useMemo(() => createPayoutsClient(getToken), [getToken]);

  useEffect(() => {
    if (!payoutsLive || !session) {
      return;
    }
    let cancelled = false;
    setPayoutState("loading");
    payoutsClient
      .getBalances()
      .then((data) => {
        if (!cancelled) {
          setBalances(data);
          setPayoutState("idle");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPayoutState("failed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [payoutsLive, payoutsClient, session]);

  const signOut = async () => {
    setSigningOut(true);
    setSignOutFailed(false);
    try {
      const { createBrowserClient } = await import("@vergeo/auth/browser-client");
      await createBrowserClient().auth.signOut();
      router.replace(`/${locale}/login`);
      router.refresh();
    } catch {
      setSigningOut(false);
      setSignOutFailed(true);
    }
  };

  const onLocaleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value;
    if (next === locale) {
      return;
    }
    const nextPath = swapLocaleInPath(pathname, next);
    const query = window.location.search;
    window.location.assign(query ? `${nextPath}${query}` : nextPath);
  };

  const contact = user?.email ?? user?.phone ?? null;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-2xl font-semibold">{t("settings.title")}</h1>
        <p className="text-sm text-text-2">{t("settings.intro")}</p>
      </header>

      <Section id="account" title={t("settings.account.heading")}>
        <p className="text-sm text-text-2">{t("settings.account.signedInAs")}</p>
        <p className="break-all text-base font-medium" data-testid="settings-contact">
          {contact ?? t("settings.account.unknown")}
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/${locale}/reset-password`}
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline"
          >
            {t("settings.account.changePassword")}
          </Link>
          <Link
            href={`/${locale}/profile`}
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline"
          >
            {t("settings.account.editProfile")}
          </Link>
        </div>
        {signOutFailed ? (
          <p role="alert" className="text-sm text-danger">
            {t("settings.account.signOutFailed")}
          </p>
        ) : null}
        <Button
          type="button"
          variant="secondary"
          loading={signingOut}
          loadingLabel={t("settings.account.signingOut")}
          data-testid="settings-sign-out"
          onClick={() => void signOut()}
        >
          {t("settings.account.signOut")}
        </Button>
      </Section>

      <Section id="notifications" title={t("settings.notifications.heading")}>
        <p className="text-sm text-text-2">{t("settings.notifications.body")}</p>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/${locale}/notifications`}
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline"
          >
            {t("settings.notifications.open")}
          </Link>
          <Link
            href={`/${locale}/profile`}
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline"
          >
            {t("settings.notifications.whatsapp")}
          </Link>
        </div>
      </Section>

      <Section id="payout" title={t("settings.payout.heading")}>
        {!payoutsLive ? (
          <p className="text-sm text-text-2">{t("settings.payout.pilot")}</p>
        ) : payoutState === "loading" ? (
          <p className="text-sm text-text-2">{t("settings.payout.loading")}</p>
        ) : payoutState === "failed" ? (
          <p role="alert" className="text-sm text-danger">
            {t("settings.payout.loadFailed")}
          </p>
        ) : balances?.payout_msisdn ? (
          <p className="text-base font-medium" data-testid="settings-payout-method">
            {t("settings.payout.current", {
              rail: (balances.payout_rail ?? "").toUpperCase(),
              number: maskMsisdn(balances.payout_msisdn),
            })}
          </p>
        ) : (
          <p className="text-sm text-text-2">{t("settings.payout.none")}</p>
        )}
        {payoutsLive ? (
          <Link
            href={`/${locale}/payouts/method`}
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline"
          >
            {t("settings.payout.change")}
          </Link>
        ) : null}
      </Section>

      <Section id="language" title={t("settings.language.heading")}>
        <FormField label={t("settings.language.label")}>
          <Select
            value={locale}
            onChange={onLocaleChange}
            data-testid="settings-locale"
            aria-label={t("settings.language.label")}
          >
            {LOCALES.map((code) => (
              <option key={code} value={code}>
                {t(`settings.language.names.${code}`)}
              </option>
            ))}
          </Select>
        </FormField>
      </Section>
    </div>
  );
}
