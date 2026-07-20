export const LOCALES = ["en", "bem", "nya", "fr", "zh"] as const;

export type Locale = (typeof LOCALES)[number];

export const PUBLIC_LOCALES = ["en", "bem", "nya", "fr"] as const satisfies readonly Locale[];

export type PublicLocale = (typeof PUBLIC_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";
