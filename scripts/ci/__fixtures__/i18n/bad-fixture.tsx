/* eslint-disable */
// @ts-nocheck
// SEEDED FIXTURE — proves scripts/ci/i18n-lint.mjs has teeth. NOT compiled or
// shipped (lives under scripts/ci/__fixtures__, outside every app tsconfig).
// Deliberately contains one of each violation the sweep must catch:
//   1. hardcoded-string  — aria-label / title template / <meta content>
//   2. missing-key       — t("…") for a key absent from every EN namespace
//   3. formatk-bypass    — `K${…}` currency prefixing + Intl.NumberFormat
import { useTranslations } from "next-intl";

// (3) formatK bypass — raw currency prefixing and Intl.NumberFormat.
function badMoney(cents: number, itemName: string): string {
  const viaIntl = new Intl.NumberFormat("en-ZM").format(cents);
  return `K${(cents / 100).toFixed(2)} ${viaIntl}`;
}

export function BadFixture({ itemName }: { itemName: string }) {
  // (2) missing key — no EN namespace defines catalog.this.key.does.not.exist.
  const t = useTranslations("catalog");

  return (
    <div>
      {/* (1) hardcoded string — user-facing aria-label literal. */}
      <button aria-label="Close the dialog now" type="button">
        {t("this.key.does.not.exist.anywhere")}
      </button>
      {/* (1) hardcoded string — template literal in a user-facing attribute. */}
      <span title={`Delete ${itemName} permanently`}>{badMoney(1000, itemName)}</span>
      {/* (1) hardcoded string — <meta> content copy. */}
      <meta content="Discover products across Zambia" name="description" />
    </div>
  );
}
