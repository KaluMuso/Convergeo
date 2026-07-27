import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ClipComposer } from "../_components/clip-composer";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const clips = vendorMessages.clips as {
    compose: { title: string };
    meta: { description: string };
  };
  return {
    title: clips.compose.title,
    description: clips.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function NewClipPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-0 sm:p-4">
      <ClipComposer />
    </main>
  );
}
