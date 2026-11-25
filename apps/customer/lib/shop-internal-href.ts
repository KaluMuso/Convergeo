import { LOCALES } from "@vergeo/i18n";

import { SERVICE_VERTICALS } from "../app/[locale]/(shop)/services/_components/service-verticals";

const SERVICE_VERTICAL_SET = new Set<string>(SERVICE_VERTICALS);

function stripLeadingLocale(href: string): { locale: string | null; path: string } {
  const segments = href.split("/").filter(Boolean);
  if (segments.length === 0) {
    return { locale: null, path: "/" };
  }
  const maybeLocale = segments[0] ?? "";
  if (LOCALES.includes(maybeLocale as (typeof LOCALES)[number])) {
    const rest = segments.slice(1).join("/");
    return { locale: maybeLocale, path: rest ? `/${rest}` : "/" };
  }
  return { locale: null, path: href.startsWith("/") ? href : `/${href}` };
}

/**
 * Rewrites bare service vertical paths (e.g. `/tech-services`) to the services
 * browse URL. Admin merchandising and legacy hrefs sometimes omit `/services`.
 */
export function repairServiceVerticalHref(href: string, locale: string): string {
  if (!href.startsWith("/") || href.startsWith("//")) {
    return href;
  }

  const { locale: embedded, path } = stripLeadingLocale(href);
  const activeLocale: string = embedded ?? locale;
  const leaf = path.split("/").filter(Boolean)[0];
  if (!leaf || !SERVICE_VERTICAL_SET.has(leaf)) {
    return href;
  }

  const params = new URLSearchParams({ category: leaf });
  return `/${activeLocale}/services?${params.toString()}`;
}
