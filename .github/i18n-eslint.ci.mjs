import vergeoPlugin from "../packages/config/eslint-rules/no-hardcoded-strings.js";
import tseslint from "typescript-eslint";

export default [
  { ignores: ["**/node_modules/**", "**/.next/**"] },
  {
    files: ["apps/**/app/**/*.{tsx,jsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        ecmaVersion: "latest",
        sourceType: "module",
      },
    },
    plugins: { "@vergeo": vergeoPlugin },
    rules: { "@vergeo/no-hardcoded-strings": "error" },
  },
];
