import { RuleTester } from "eslint";
import tsParser from "@typescript-eslint/parser";
import { describe, it } from "vitest";

import vergeoPlugin from "./no-hardcoded-strings.js";

const ruleTester = new RuleTester({
  languageOptions: {
    parser: tsParser,
    parserOptions: {
      ecmaFeatures: { jsx: true },
      ecmaVersion: "latest",
      sourceType: "module",
    },
  },
});

describe("@vergeo/no-hardcoded-strings", () => {
  it("runs rule fixtures", () => {
    ruleTester.run("@vergeo/no-hardcoded-strings", vergeoPlugin.rules["no-hardcoded-strings"], {
      valid: [
        '<div className="x" />',
        "<span>{formatK(price)}</span>",
        '<input placeholder={t("search.placeholder")} />',
        "<img alt={label} />",
      ],
      invalid: [
        {
          code: "<div>Hello world</div>",
          errors: [{ messageId: "noHardcoded" }],
        },
        {
          code: '<input placeholder="Search products" />',
          errors: [{ messageId: "noHardcoded" }],
        },
        {
          code: '<img alt="Product photo" />',
          errors: [{ messageId: "noHardcoded" }],
        },
      ],
    });
  });
});
