import { loadNamespace, type Locale } from "@vergeo/i18n";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { AskThread } from "../_components/ask/ask-thread";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string }>;
};

/**
 * The `ai` namespace is stored as fully-qualified flat keys (e.g. `ai.ask.title`).
 * next-intl resolves keys by splitting on `.`, so we un-flatten into a nested tree
 * (`{ ai: { ask: { title } } }`) before handing it to the provider/translator.
 */
function unflatten(flat: Record<string, string>): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split(".");
    const leaf = parts.pop();
    if (leaf === undefined) {
      continue;
    }
    let node = root;
    for (const part of parts) {
      const existing = node[part];
      if (typeof existing === "object" && existing !== null) {
        node = existing as Record<string, unknown>;
      } else {
        const next: Record<string, unknown> = {};
        node[part] = next;
        node = next;
      }
    }
    node[leaf] = value;
  }
  return root;
}

async function getAiMessages(locale: string): Promise<Record<string, unknown>> {
  const aiFlat = (await loadNamespace(locale as Locale, "ai")) as Record<string, string>;
  return unflatten(aiFlat);
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const messages = await getAiMessages(locale);
  const t = createTranslator({
    locale,
    messages: messages as AbstractIntlMessages,
    namespace: "ai",
  });

  return {
    title: t("ask.title"),
    description: t("ask.subtitle"),
    // User-specific, dynamic answers — keep out of the index.
    robots: { index: false, follow: false },
  };
}

export default async function AskPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { q } = await searchParams;
  setRequestLocale(locale);

  const messages = await getAiMessages(locale);

  return (
    <NextIntlClientProvider locale={locale} messages={messages as AbstractIntlMessages}>
      <div className="lg:mx-auto lg:w-full lg:max-w-3xl">
        <AskThread locale={locale} initialQuery={q?.trim() ?? ""} />
      </div>
    </NextIntlClientProvider>
  );
}
