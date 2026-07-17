// Translation-catalog primitives for the admin translator. Unlike loadNamespace
// (which falls back to English for a missing file/key), these expose each locale's
// OWN content so coverage — which keys a locale actually translates vs. inherits
// from English — can be computed.

import { type Locale } from "./locales";
import { type Namespace } from "./request";

type RawMessages = { [key: string]: string | RawMessages };

/**
 * A locale's raw messages for one namespace, WITHOUT English fallback. Returns
 * null when the locale has no file for that namespace (the coverage "gap" signal).
 */
export async function loadRawNamespace(
  locale: Locale,
  namespace: Namespace,
): Promise<RawMessages | null> {
  try {
    const mod = (await import(`../messages/${locale}/${namespace}.json`)) as {
      default: RawMessages;
    };
    return mod.default;
  } catch {
    return null;
  }
}

/** Flatten nested messages to dotted keys → string values (ICU templates as-is). */
export function flattenMessages(messages: RawMessages, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(messages)) {
    const dotted = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object") {
      Object.assign(out, flattenMessages(value, dotted));
    } else {
      out[dotted] = String(value);
    }
  }
  return out;
}

/** Flat dotted keys a locale defines for a namespace ([] when it has no file). */
export async function localeNamespaceKeys(locale: Locale, namespace: Namespace): Promise<string[]> {
  const raw = await loadRawNamespace(locale, namespace);
  return raw ? Object.keys(flattenMessages(raw)) : [];
}
