import { describe, expect, it } from "vitest";

import {
  charCount,
  draftToPayload,
  emptyDraft,
  validateDraft,
  type CategoryPresentationDraft,
} from "./category-presentation-api";

function draft(overrides: Partial<CategoryPresentationDraft>): CategoryPresentationDraft {
  return { ...emptyDraft(), ...overrides };
}

describe("validateDraft", () => {
  it("flags an empty draft", () => {
    expect(validateDraft(emptyDraft())).toEqual([{ kind: "empty" }]);
  });

  it("accepts a 60-character title and rejects 61", () => {
    expect(validateDraft(draft({ banner_title_i18n: { en: "a".repeat(60) } }))).toEqual([]);
    expect(validateDraft(draft({ banner_title_i18n: { en: "a".repeat(61) } }))).toContainEqual({
      kind: "titleTooLong",
      locale: "en",
    });
  });

  it("rejects a description over 160 characters in any locale", () => {
    const problems = validateDraft(
      draft({
        banner_title_i18n: { en: "Title" },
        banner_description_i18n: { en: "ok", nya: "b".repeat(161) },
      }),
    );
    expect(problems).toContainEqual({ kind: "descriptionTooLong", locale: "nya" });
  });

  it("requires English when another locale has text", () => {
    expect(validateDraft(draft({ banner_title_i18n: { bem: "Ifya kulya" } }))).toContainEqual({
      kind: "englishRequired",
    });
  });

  it("requires a title before a description", () => {
    expect(
      validateDraft(draft({ icon_public_id: "x", banner_description_i18n: { en: "Words" } })),
    ).toContainEqual({ kind: "descriptionNeedsTitle" });
  });

  it("counts collapsed whitespace and code points like the API", () => {
    expect(charCount("  two   words ")).toBe(9);
    expect(charCount("🙂🙂")).toBe(2);
  });
});

describe("draftToPayload", () => {
  it("drops empty locales and blank images", () => {
    expect(
      draftToPayload(
        draft({
          banner_title_i18n: { en: "  Fresh  food ", fr: "   " },
          banner_public_id: "categories/banners/x",
        }),
      ),
    ).toEqual({
      icon_public_id: null,
      banner_public_id: "categories/banners/x",
      banner_title_i18n: { en: "Fresh food" },
      banner_description_i18n: {},
    });
  });
});
