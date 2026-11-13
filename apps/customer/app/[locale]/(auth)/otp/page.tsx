import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { redirect } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { maskPhone } from "../_components/auth-utils";
import { OtpForm } from "../_components/otp-form";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ phone?: string; next?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function OtpPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { phone, next } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  if (!phone) {
    redirect(`/${locale}/login`);
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const authMessages = await loadNamespace(locale as Locale, "auth");
  const messages = { ...baseMessages, auth: authMessages } as AbstractIntlMessages;

  const t = createTranslator({ locale, messages, namespace: "auth" });
  // These labels cross the server→client boundary, so they must be serializable
  // strings, not functions. Client components interpolate the `{…}` placeholders.
  // t.raw returns the literal ICU template (t() would drop unfilled placeholders).
  const throttled = String(t.raw("errors.throttled"));
  const digitLabel = String(t.raw("otp.digitLabel"));
  const resendIn = String(t.raw("otp.resendIn"));
  const sentMessage = String(t.raw("otp.sent")).replace("{phone}", maskPhone(phone));

  const labels = {
    ariaGroup: t("otp.ariaGroup"),
    digitLabel,
    submit: t("otp.submit"),
    loading: t("loading.verify"),
    resend: t("otp.resend"),
    resendIn,
    changePhone: t("otp.changePhone"),
    wrongCode: t("errors.wrongCode"),
    expired: t("errors.expired"),
    throttled,
    generic: t("errors.generic"),
    sendFailed: t("errors.sendFailed"),
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="space-y-1.5 text-center">
        <h1 className="font-display text-h2 text-display-ink">{t("otp.title")}</h1>
        <p className="font-body text-sm text-text-2">{sentMessage}</p>
      </header>

      <OtpForm
        locale={locale}
        phone={phone}
        labels={labels}
        loginPath="/login"
        defaultNextPath={`/${locale}`}
        nextParam={next}
      />

      <details
        className="group rounded-card border border-border bg-surface px-4 py-3"
        data-testid="otp-help"
      >
        <summary className="flex min-h-11 cursor-pointer items-center font-body text-sm font-semibold text-text focus-visible:outline-none focus-visible:shadow-focusRing">
          {t("otp.help.title")}
        </summary>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 font-body text-sm text-text-2">
          <li>{t("otp.help.checkNumber")}</li>
          <li>{t("otp.help.wait")}</li>
          <li>{t("otp.help.resend")}</li>
          <li>
            {t("otp.help.support")}{" "}
            <Link
              href={`/${locale}/contact`}
              className="font-medium text-primary underline-offset-2 hover:underline"
            >
              {t("otp.help.supportCta")}
            </Link>
          </li>
        </ul>
      </details>

      <Link href={`/${locale}/login`} className="sr-only">
        {t("otp.changePhone")}
      </Link>
    </div>
  );
}
