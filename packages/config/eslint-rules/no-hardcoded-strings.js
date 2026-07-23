/** @type {import('eslint').Rule.RuleModule} */
const noHardcodedStringsRule = {
  meta: {
    type: "suggestion",
    docs: {
      description:
        "Disallow hardcoded user-facing strings in JSX text nodes and user-facing attributes",
    },
    schema: [],
    messages: {
      noHardcoded:
        "Use next-intl message keys instead of hardcoded user-facing strings (@vergeo/no-hardcoded-strings).",
    },
  },
  create(context) {
    const filename = context.filename ?? context.getFilename?.() ?? "";

    if (shouldIgnoreFile(filename)) {
      return {};
    }

    return {
      JSXText(node) {
        const text = node.value.replace(/\s+/g, " ").trim();
        // Skip text with no translatable letters — pure separators/punctuation
        // ("·", ":", "—", numbers) are not user-facing copy and need no key.
        if (text.length > 0 && /\p{L}/u.test(text)) {
          context.report({ node, messageId: "noHardcoded" });
        }
      },
      JSXAttribute(node) {
        if (node.type !== "JSXAttribute" || node.name.type !== "JSXIdentifier") {
          return;
        }

        const attributeName = node.name.name;
        if (!isUserFacingAttribute(attributeName)) {
          return;
        }

        if (isStringLiteral(node.value)) {
          context.report({ node, messageId: "noHardcoded" });
        }
      },
    };
  },
};

const USER_FACING_ATTRIBUTES = new Set(["placeholder", "title", "alt", "aria-label"]);

const IGNORED_PATH_SEGMENTS = [
  "/services/",
  "/node_modules/",
  ".test.",
  ".spec.",
  "__tests__",
  // OG / social-card generators render brand-language images, not localized UI.
  "opengraph-image",
  "twitter-image",
];

function shouldIgnoreFile(filename) {
  return IGNORED_PATH_SEGMENTS.some((segment) => filename.includes(segment));
}

function isUserFacingAttribute(name) {
  return USER_FACING_ATTRIBUTES.has(name);
}

function isStringLiteral(value) {
  if (!value) {
    return false;
  }

  if (
    value.type === "Literal" &&
    typeof value.value === "string" &&
    value.value.trim().length > 0
  ) {
    return true;
  }

  return false;
}

/** @type {import('eslint').ESLint.Plugin} */
const vergeoPlugin = {
  rules: {
    "no-hardcoded-strings": noHardcodedStringsRule,
  },
};

export default vergeoPlugin;
