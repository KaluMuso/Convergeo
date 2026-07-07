/** @type {import('eslint').Rule.RuleModule} */
const noHardcodedStringsRule = {
  meta: {
    type: "suggestion",
    docs: {
      description:
        "Disallow hardcoded user-facing strings in JSX text nodes (stub — hardened in M16-P03)",
    },
    schema: [],
    messages: {
      noHardcoded: "Use next-intl message keys instead of hardcoded JSX text.",
    },
  },
  create(context) {
    return {
      JSXText(node) {
        const text = node.value.replace(/\s+/g, " ").trim();
        if (text.length > 0) {
          context.report({
            node,
            messageId: "noHardcoded",
          });
        }
      },
    };
  },
};

/** @type {import('eslint').ESLint.Plugin} */
const plugin = {
  rules: {
    "no-hardcoded-strings": noHardcodedStringsRule,
  },
};

export default plugin;
