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
  const throttled = (seconds: number) =>
    t("errors.throttled").replace("{seconds}", String(seconds));
  const digitLabel = (position: number, total: number) =>
    t("otp.digitLabel").replace("{position}", String(position)).replace("{total}", String(total));
  const resendIn = (seconds: number) => t("otp.resendIn").replace("{seconds}", String(seconds));
  const sentMessage = t("otp.sent").replace("{phone}", maskPhone(phone));

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
      <header className="space-y-2 text-center">
        <h1 className="font-display text-2xl text-display-ink">{t("otp.title")}</h1>
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

      <Link href={`/${locale}/login`} className="sr-only">
        {t("otp.changePhone")}
      </Link>
    </div>
  );
}
