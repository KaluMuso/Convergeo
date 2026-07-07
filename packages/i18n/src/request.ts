import { getRequestConfig } from "next-intl/server";

import { DEFAULT_LOCALE, LOCALES, type Locale } from "./locales";

export const NAMESPACES = [
  "common",
  "auth",
  "catalog",
  "search",
  "checkout",
  "orders",
  "vendor",
  "admin",
  "events",
  "services",
  "supplies",
  "directory",
  "legal",
  "notifications",
  "account",
  "ai",
] as const;

export type Namespace = (typeof NAMESPACES)[number];

type Messages = { [key: string]: string | Messages };

const namespaceCache = new Map<string, Messages>();

function cacheKey(locale: Locale, namespace: Namespace): string {
  return `${locale}:${namespace}`;
}

export function clearMessageCache(): void {
  namespaceCache.clear();
}

export function getLoadedNamespaceKeys(): string[] {
  return [...namespaceCache.keys()];
}

const namespaceLoaders: Record<Namespace, (locale: Locale) => Promise<Messages>> = {
  common: (locale) => import(`../messages/${locale}/common.json`).then((m) => m.default),
  auth: (locale) => import(`../messages/${locale}/auth.json`).then((m) => m.default),
  catalog: (locale) => import(`../messages/${locale}/catalog.json`).then((m) => m.default),
  search: (locale) => import(`../messages/${locale}/search.json`).then((m) => m.default),
  checkout: (locale) => import(`../messages/${locale}/checkout.json`).then((m) => m.default),
  orders: (locale) => import(`../messages/${locale}/orders.json`).then((m) => m.default),
  vendor: (locale) => import(`../messages/${locale}/vendor.json`).then((m) => m.default),
  admin: (locale) => import(`../messages/${locale}/admin.json`).then((m) => m.default),
  events: (locale) => import(`../messages/${locale}/events.json`).then((m) => m.default),
  services: (locale) => import(`../messages/${locale}/services.json`).then((m) => m.default),
  supplies: (locale) => import(`../messages/${locale}/supplies.json`).then((m) => m.default),
  directory: (locale) => import(`../messages/${locale}/directory.json`).then((m) => m.default),
  legal: (locale) => import(`../messages/${locale}/legal.json`).then((m) => m.default),
  notifications: (locale) =>
    import(`../messages/${locale}/notifications.json`).then((m) => m.default),
  account: (locale) => import(`../messages/${locale}/account.json`).then((m) => m.default),
  ai: (locale) => import(`../messages/${locale}/ai.json`).then((m) => m.default),
};

export async function loadNamespace(locale: Locale, namespace: Namespace): Promise<Messages> {
  const key = cacheKey(locale, namespace);
  const cached = namespaceCache.get(key);
  if (cached) {
    return cached;
  }

  try {
    const messages = await namespaceLoaders[namespace](locale);
    namespaceCache.set(key, messages);
    return messages;
  } catch {
    if (locale !== DEFAULT_LOCALE) {
      return loadNamespace(DEFAULT_LOCALE, namespace);
    }
    namespaceCache.set(key, {});
    return {};
  }
}

export async function loadMessages(
  locale: Locale,
  namespaces: readonly Namespace[] = ["common"],
): Promise<Record<Namespace, Messages>> {
  const entries = await Promise.all(
    namespaces.map(
      async (namespace) => [namespace, await loadNamespace(locale, namespace)] as const,
    ),
  );

  return Object.fromEntries(entries) as Record<Namespace, Messages>;
}

function parseMessageKey(key: string): { namespace: Namespace; messageKey: string } {
  const dotIndex = key.indexOf(".");
  if (dotIndex === -1) {
    return { namespace: "common", messageKey: key };
  }

  const first = key.slice(0, dotIndex);
  if ((NAMESPACES as readonly string[]).includes(first)) {
    return { namespace: first as Namespace, messageKey: key };
  }

  return { namespace: "common", messageKey: key };
}

function getMessage(messages: Messages, key: string): string | undefined {
  const direct = messages[key];
  if (typeof direct === "string") {
    return direct;
  }
  let node: string | Messages | undefined = messages;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === undefined) {
      return undefined;
    }
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

export async function resolveMessage(
  locale: Locale,
  key: string,
  values?: Record<string, string | number>,
): Promise<string> {
  const { namespace, messageKey } = parseMessageKey(key);
  const messages = await loadNamespace(locale, namespace);
  const fallbackMessages =
    locale === DEFAULT_LOCALE ? messages : await loadNamespace(DEFAULT_LOCALE, namespace);

  const template =
    getMessage(messages, messageKey) ?? getMessage(fallbackMessages, messageKey) ?? key;
  return interpolate(template, values);
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
  const messages = await loadMessages(resolvedLocale, ["common"]);

  return {
    locale: resolvedLocale,
    messages,
    getMessageFallback({ key }) {
      return key;
    },
  };
});
