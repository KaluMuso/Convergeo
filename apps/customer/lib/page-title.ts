import { loadNamespace, type Locale, type Namespace } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";

import type { Metadata } from "next";

/**
 * Localised `<title>` for a page, from the same message key as its visible heading.
 * The root layout supplies the `%s | Convergeo` template, so this returns just the
 * page name. Server-only: costs no client JS.
 */
export async function getPageTitle(
  locale: string,
  namespace: Namespace,
  key: string,
  values?: Record<string, string | number>,
): Promise<string> {
  const messages = {
    [namespace]: await loadNamespace(locale as Locale, namespace),
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace }) as unknown as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;
  return t(key, values);
}

/** `title`, plus the page's robots policy when it is not indexed. */
export async function buildPageMetadata(
  locale: string,
  namespace: Namespace,
  key: string,
  robots?: Metadata["robots"],
): Promise<Metadata> {
  const title = await getPageTitle(locale, namespace, key);
  return robots === undefined ? { title } : { title, robots };
}
