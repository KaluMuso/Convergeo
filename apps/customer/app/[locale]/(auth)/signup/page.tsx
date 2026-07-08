import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { AuthSignupShell } from "../_components/login-shell";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function SignupPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { next } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const authMessages = await loadNamespace(locale as Locale, "auth");
  const messages = { ...baseMessages, auth: authMessages } as AbstractIntlMessages;

  const t = createTranslator({ locale, messages, namespace: "auth" });
  const throttled = (seconds: number) =>
    t("errors.throttled").replace("{seconds}", String(seconds));

  const labels = {
    title: t("signup.title"),
    subtitle: t("signup.subtitle"),
    phone: {
      countryCode: t("login.countryCode"),
      nationalNumber: t("login.nationalNumber"),
      phoneLabel: t("signup.phoneLabel"),
      phoneHelp: t("signup.phoneHelp"),
      phonePlaceholder: t("login.phonePlaceholder"),
      submit: t("signup.submit"),
      loading: t("loading.submit"),
      required: t("errors.required"),
      invalidPhone: t("errors.invalidPhone"),
      sendFailed: t("errors.sendFailed"),
      throttled,
    },
    email: {
      emailLabel: t("email.emailLabel"),
      passwordLabel: t("email.passwordLabel"),
      submit: t("email.submitSignup"),
      loading: t("loading.submit"),
      required: t("errors.required"),
      invalidEmail: t("errors.invalidEmail"),
      invalidPassword: t("errors.invalidPassword"),
      generic: t("errors.generic"),
      throttled,
    },
    divider: t("signup.divider"),
    emailToggle: t("signup.emailToggle"),
    phoneToggle: t("signup.phoneToggle"),
    google: t("signup.google"),
    googleLoading: t("google.loading"),
    loginPrompt: t("signup.hasAccount"),
    loginLink: t("signup.loginLink"),
    genericError: t("errors.generic"),
  };

  return (
    <AuthSignupShell
      locale={locale}
      labels={labels}
      defaultNextPath={`/${locale}`}
      nextParam={next}
    />
  );
}
