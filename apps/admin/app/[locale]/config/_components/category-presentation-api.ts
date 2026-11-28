/** Admin category icon / banner / banner copy (PUT/DELETE /admin/config/categories/{id}/presentation). */

export const PRESENTATION_LOCALES = ["en", "bem", "nya", "fr", "zh"] as const;
export type PresentationLocale = (typeof PRESENTATION_LOCALES)[number];

export const MAX_BANNER_TITLE_CHARS = 60;
export const MAX_BANNER_DESCRIPTION_CHARS = 160;

export type LocaleCopy = Partial<Record<PresentationLocale, string>>;

export type CategoryPresentation = {
  category_id: string;
  slug: string;
  icon_public_id: string | null;
  banner_public_id: string | null;
  banner_title_i18n: LocaleCopy;
  banner_description_i18n: LocaleCopy;
  updated_at?: string | null;
};

export type CategoryPresentationDraft = {
  icon_public_id: string;
  banner_public_id: string;
  banner_title_i18n: LocaleCopy;
  banner_description_i18n: LocaleCopy;
};

export type DraftProblem =
  | { kind: "titleTooLong"; locale: PresentationLocale }
  | { kind: "descriptionTooLong"; locale: PresentationLocale }
  | { kind: "englishRequired" }
  | { kind: "descriptionNeedsTitle" }
  | { kind: "empty" };

export function emptyDraft(): CategoryPresentationDraft {
  return {
    icon_public_id: "",
    banner_public_id: "",
    banner_title_i18n: {},
    banner_description_i18n: {},
  };
}

export function draftFromPresentation(
  presentation: CategoryPresentation | undefined,
): CategoryPresentationDraft {
  if (!presentation) {
    return emptyDraft();
  }
  return {
    icon_public_id: presentation.icon_public_id ?? "",
    banner_public_id: presentation.banner_public_id ?? "",
    banner_title_i18n: { ...presentation.banner_title_i18n },
    banner_description_i18n: { ...presentation.banner_description_i18n },
  };
}

/** Same whitespace rule as the API: trim and collapse runs of spaces. */
export function normalizeCopyText(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(" ");
}

function cleanCopy(copy: LocaleCopy): LocaleCopy {
  const cleaned: LocaleCopy = {};
  for (const locale of PRESENTATION_LOCALES) {
    const text = normalizeCopyText(copy[locale] ?? "");
    if (text) {
      cleaned[locale] = text;
    }
  }
  return cleaned;
}

/** Character count as the API counts it (Unicode code points, not UTF-16 units). */
export function charCount(value: string): number {
  return Array.from(normalizeCopyText(value)).length;
}

/** Client-side mirror of the API's validation, so the admin sees problems before saving. */
export function validateDraft(draft: CategoryPresentationDraft): DraftProblem[] {
  const problems: DraftProblem[] = [];
  const titles = cleanCopy(draft.banner_title_i18n);
  const descriptions = cleanCopy(draft.banner_description_i18n);
  for (const locale of PRESENTATION_LOCALES) {
    if (charCount(titles[locale] ?? "") > MAX_BANNER_TITLE_CHARS) {
      problems.push({ kind: "titleTooLong", locale });
    }
    if (charCount(descriptions[locale] ?? "") > MAX_BANNER_DESCRIPTION_CHARS) {
      problems.push({ kind: "descriptionTooLong", locale });
    }
  }
  const hasTitles = Object.keys(titles).length > 0;
  const hasDescriptions = Object.keys(descriptions).length > 0;
  if ((hasTitles && !titles.en) || (hasDescriptions && !descriptions.en)) {
    problems.push({ kind: "englishRequired" });
  }
  if (hasDescriptions && !hasTitles) {
    problems.push({ kind: "descriptionNeedsTitle" });
  }
  if (!draft.icon_public_id && !draft.banner_public_id && !hasTitles && !hasDescriptions) {
    problems.push({ kind: "empty" });
  }
  return problems;
}

export function draftToPayload(draft: CategoryPresentationDraft) {
  return {
    icon_public_id: draft.icon_public_id || null,
    banner_public_id: draft.banner_public_id || null,
    banner_title_i18n: cleanCopy(draft.banner_title_i18n),
    banner_description_i18n: cleanCopy(draft.banner_description_i18n),
  };
}
