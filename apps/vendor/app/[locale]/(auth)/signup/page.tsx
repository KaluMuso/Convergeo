import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { AuthSignupShell } from "../../../../../customer/app/[locale]/(auth)/_components/login-shell";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/**
 * Self-serve seller sign-up (Start selling → sign-up → KYC). Creates a plain
 * account only; the vendor role is granted by admin approval after KYC, and
 * the middleware sends new accounts to /onboarding until then.
 */
export default async function VendorSignupPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { next } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const authMessages = await loadNamespace(locale as Locale, "auth");
  const commonMessages = await loadNamespace(locale as Locale, "common");
  const messages = {
    ...baseMessages,
    auth: authMessages,
    common: commonMessages,
  } as AbstractIntlMessages;

  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const t = createTranslator({ locale, messages, namespace: "auth" });
  const throttled = String(t.raw("errors.throttled"));

  const labels = {
    title: t("signup.vendorTitle"),
    subtitle: t("signup.vendorSubtitle"),
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
      invalidCredentials: t("errors.invalidCredentials"),
      emailNotConfirmed: t("errors.emailNotConfirmed"),
      alreadyRegistered: t("errors.alreadyRegistered"),
      signupConfirmation: t("signup.emailConfirmation"),
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
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="flex items-center justify-center px-4 py-6">
        <p className="font-display text-lg text-display-ink">{tCommon("app.name")}</p>
      </header>
      <main className="mx-auto flex w-full max-w-[360px] flex-1 flex-col px-4 pb-8">
        <AuthSignupShell
          locale={locale}
          portal="vendor"
          labels={labels}
          defaultNextPath={`/${locale}/onboarding`}
          nextParam={next}
        />
      </main>
    </div>
  );
}
