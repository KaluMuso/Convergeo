import { loadNamespace, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages } from "next-intl/server";

import type { ReactNode } from "react";

export type LegalTranslator = {
  (key: string, values?: Record<string, string | number>): string;
  rich: (key: string, values: Record<string, (chunks: ReactNode) => ReactNode>) => ReactNode;
};

export async function getLegalTranslator(locale: string): Promise<LegalTranslator> {
  const baseMessages = await getMessages();
  const legalMessages = await loadNamespace(locale as Locale, "legal");
  const messages = { ...baseMessages, legal: legalMessages } as AbstractIntlMessages;
  return createTranslator({
    locale,
    messages,
    namespace: "legal",
  }) as unknown as LegalTranslator;
}

export type LegalSection = {
  id: string;
  heading: ReactNode;
  body: ReactNode;
};

export type LegalShellProps = {
  title: ReactNode;
  updatedLabel: ReactNode;
  counselNote: ReactNode;
  tocLabel: ReactNode;
  sections: LegalSection[];
  afterSections?: ReactNode;
};

export function LegalShell({
  title,
  updatedLabel,
  counselNote,
  tocLabel,
  sections,
  afterSections,
}: LegalShellProps) {
  return (
    <main id="marketing-main" className="mx-auto w-full max-w-2xl px-4 py-8">
      <header className="mb-8 space-y-4">
        <h1 className="font-display text-h1 text-display-ink">{title}</h1>
        <p className="text-sm text-text-2">{updatedLabel}</p>
        <aside
          className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-text"
          role="note"
        >
          {counselNote}
        </aside>
      </header>

      {sections.length > 0 ? (
        <nav
          aria-label={typeof tocLabel === "string" ? tocLabel : undefined}
          className="mb-8 rounded-lg border border-border bg-bg-2 p-4"
        >
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-2">
            {tocLabel}
          </h2>
          <ul className="flex flex-col gap-2 text-sm">
            {sections.map((section) => (
              <li key={section.id}>
                <a
                  className="inline-flex min-h-11 items-center text-primary underline-offset-2 hover:underline"
                  href={`#${section.id}`}
                >
                  {section.heading}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}

      <article className="space-y-10">
        {sections.map((section) => (
          <section key={section.id} id={section.id} className="scroll-mt-24 space-y-3">
            <h2 className="font-display text-h2 text-display-ink">{section.heading}</h2>
            <div className="text-body leading-relaxed text-text">{section.body}</div>
          </section>
        ))}
        {afterSections}
      </article>
    </main>
  );
}
