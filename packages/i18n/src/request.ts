import { getRequestConfig } from "next-intl/server";

import { DEFAULT_LOCALE, LOCALES, type Locale } from "./locales";

type Messages = Record<string, unknown>;

const messageCache = new Map<string, Messages>();

export async function loadMessages(locale: Locale): Promise<Messages> {
  const cached = messageCache.get(locale);
  if (cached) {
    return cached;
  }

  try {
    const module = await import(`../messages/${locale}/common.json`);
    const messages = module.default as Messages;
    messageCache.set(locale, messages);
    return messages;
  } catch {
    if (locale !== DEFAULT_LOCALE) {
      return loadMessages(DEFAULT_LOCALE);
    }
    return {};
  }
}

export async function resolveMessage(
  locale: Locale,
  key: string,
  values?: Record<string, string | number>,
): Promise<string> {
  const messages = await loadMessages(locale);
  const fallbackMessages =
    locale === DEFAULT_LOCALE ? messages : await loadMessages(DEFAULT_LOCALE);

  const template = getNestedValue(messages, key) ?? getNestedValue(fallbackMessages, key) ?? key;
  return interpolate(template, values);
}

function getNestedValue(messages: Messages, key: string): string | undefined {
  const value = messages[key];
  return typeof value === "string" ? value : undefined;
}

function interpolate(template: string, values?: Record<string, string | number>): string {
  if (!values) {
    return template;
  }

  return template.replace(/\{(\w+)\}/g, (_, token: string) => {
    const value = values[token];
    return value === undefined ? `{${token}}` : String(value);
  });
}

function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

export default getRequestConfig(async ({ locale }) => {
  const resolvedLocale = locale && isLocale(locale) ? locale : DEFAULT_LOCALE;
  const messages = await loadMessages(resolvedLocale);

  return {
    locale: resolvedLocale,
    messages: { common: messages },
    getMessageFallback({ key }) {
      return key;
    },
  };
});
