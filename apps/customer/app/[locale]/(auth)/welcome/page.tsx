import { createServerClient } from "@vergeo/auth/server-client";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { createAccountApiClient } from "../../account/_components/account-api";
import { getLocaleSwitcherLabels } from "../../account/_components/account-server";
import { isOnboardingComplete, resolvePostAuthPath } from "../_components/auth-utils";

import { WelcomeForm, type WelcomeFormLabels } from "./_components/welcome-form";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function WelcomePage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { next } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);

  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect(`/${locale}/login?next=/${locale}/welcome`);
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();
  const accessToken = session?.access_token;

  if (accessToken) {
    const api = createAccountApiClient(() => accessToken);
    const preferences = await api.getPreferences();
    if (isOnboardingComplete(preferences.onboarding)) {
      redirect(resolvePostAuthPath(locale, next, `/${locale}`));
    }
  }

  const baseMessages = await getMessages();
  const authMessages = await loadNamespace(locale as Locale, "auth");
  const messages = { ...baseMessages, auth: authMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "auth" });
  const localeSwitcherLabels = await getLocaleSwitcherLabels(locale);

  const labels: WelcomeFormLabels = {
    languageLabel: t("welcome.languageLabel"),
    interestsLabel: t("welcome.interestsLabel"),
    interestsHelp: t("welcome.interestsHelp"),
    interests: {
      electronics: t("welcome.interests.electronics"),
      fashion: t("welcome.interests.fashion"),
      groceries: t("welcome.interests.groceries"),
      services: t("welcome.interests.services"),
      events: t("welcome.interests.events"),
    },
    continue: t("welcome.continue"),
    continuing: t("welcome.continuing"),
    skip: t("welcome.skip"),
    error: t("welcome.error"),
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="space-y-1.5 text-center">
        <h1 className="font-display text-h2 text-display-ink">{t("welcome.title")}</h1>
        <p className="font-body text-sm text-text-2">{t("welcome.subtitle")}</p>
      </header>

      <WelcomeForm
        locale={locale}
        labels={labels}
        localeSwitcherLabels={localeSwitcherLabels}
        nextParam={next}
      />
    </div>
  );
}
