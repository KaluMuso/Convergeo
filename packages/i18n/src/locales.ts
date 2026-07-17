export const LOCALES = ["en", "bem", "nya", "fr", "zh"] as const;

export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";
