/** Client-safe Help search — no Node built-ins, so it is safe to bundle for the browser. */

/** Help article category keys — mirror `marketing.help.categories.*` i18n keys. */
export const HELP_CATEGORIES = [
  "escrow",
  "buying",
  "delivery",
  "returns",
  "events",
  "selling",
  "account",
] as const;

export type HelpCategory = (typeof HELP_CATEGORIES)[number];

/** Lightweight document shipped to the client for instant search (no bodies). */
export type HelpSearchDoc = {
  slug: string;
  title: string;
  summary: string;
  category: HelpCategory;
  keywords: string[];
};

export function isHelpCategory(value: string): value is HelpCategory {
  return (HELP_CATEGORIES as readonly string[]).includes(value);
}

/** Pure keyword search over the lightweight index — returns the full list for an empty query. */
export function searchArticles(index: HelpSearchDoc[], rawQuery: string): HelpSearchDoc[] {
  const query = rawQuery.trim().toLowerCase();
  if (query.length === 0) {
    return index;
  }
  const terms = query.split(/\s+/).filter(Boolean);

  const scored = index
    .map((doc) => {
      const haystack = [doc.title, doc.summary, doc.category, ...doc.keywords]
        .join(" ")
        .toLowerCase();
      let score = 0;
      for (const term of terms) {
        if (doc.title.toLowerCase().includes(term)) {
          score += 3;
        }
        if (doc.keywords.some((keyword) => keyword.includes(term))) {
          score += 2;
        }
        if (haystack.includes(term)) {
          score += 1;
        }
      }
      return { doc, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);

  return scored.map((entry) => entry.doc);
}
