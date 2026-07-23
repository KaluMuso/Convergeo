import { createServerClient } from "@vergeo/auth/server-client";
import { loadNamespace, type Locale } from "@vergeo/i18n";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages } from "next-intl/server";

import type { LocaleSwitcherLabels } from "../../_components/locale-switcher";

export type AccountTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function requireAccountSession(locale: string) {
  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect(`/${locale}/login?next=/${locale}/account`);
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();

  return {
    user,
    accessToken: session?.access_token ?? null,
  };
}

export async function getAccountAccessToken(locale: string): Promise<string> {
  const session = await requireAccountSession(locale);
  if (!session.accessToken) {
    redirect(`/${locale}/login?next=/${locale}/account`);
  }
  return session.accessToken;
}

export async function requireAuthenticatedAccount(locale: string): Promise<void> {
  await requireAccountSession(locale);
}

export async function getAccountTranslator(locale: string): Promise<AccountTranslator> {
  const baseMessages = await getMessages();
  const accountMessages = await loadNamespace(locale as Locale, "account");
  const messages = { ...baseMessages, account: accountMessages } as AbstractIntlMessages;
  return createTranslator({
    locale,
    messages,
    namespace: "account",
  }) as unknown as AccountTranslator;
}

/**
 * Locale-switcher labels sourced from the already-translated `common.locale.*`
 * keys (same set the shop/account headers use). Lets account pages surface a
 * language control without introducing new i18n keys.
 */
export async function getLocaleSwitcherLabels(locale: string): Promise<LocaleSwitcherLabels> {
  const baseMessages = await getMessages();
  const commonMessages = await loadNamespace(locale as Locale, "common");
  const messages = { ...baseMessages, common: commonMessages } as AbstractIntlMessages;
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  return {
    ariaLabel: tCommon("locale.switchAria"),
    names: {
      en: tCommon("locale.names.en"),
      bem: tCommon("locale.names.bem"),
      nya: tCommon("locale.names.nya"),
      fr: tCommon("locale.names.fr"),
    },
  };
}
