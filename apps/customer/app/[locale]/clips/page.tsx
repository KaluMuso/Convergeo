import { createServerClient } from "@vergeo/auth/server-client";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { absoluteApiUrl } from "../../../lib/api-base-url";
import { fetchJson } from "../../../lib/fetch-json";

import { ClipsFeed } from "./_components/clips-feed";
import { FeedError } from "./_components/feed-states";

import type { ClipFeedPage } from "./_components/types";
import type { Metadata } from "next";

/**
 * M17-P04 — the customer Clips route.
 *
 * Server-rendered on purpose: the first page of the feed (posters, captions,
 * sizes) arrives as HTML, so the route's client JS carries interaction only. The
 * whole surface sits behind the `clips` feature flag (F-V1) — while it is off the
 * route 404s, which is what makes M17 safe to merge before the Cloudinary plan
 * question (F-V4) is answered: with no entry point, no clip can be uploaded and
 * no transcode credit can be spent.
 */

export const metadata: Metadata = {
  // The indexable, shareable surface is the per-clip page (M17-P08). The feed
  // itself is a personalised-order browse surface with no index-critical content.
  robots: { index: false, follow: true },
};

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

async function clipsEnabled(): Promise<boolean> {
  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    const { data } = await supabase
      .from("feature_flags")
      .select("enabled")
      .eq("flag", "clips")
      .maybeSingle();
    return Boolean(data?.enabled);
  } catch {
    // Fail closed. An unreadable flag is not permission to open the feature.
    return false;
  }
}

export default async function ClipsPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);

  if (!(await clipsEnabled())) {
    notFound();
  }

  const clipsMessages = await loadNamespace(locale as Locale, "clips");
  const feedUrl = absoluteApiUrl("/clips/feed");

  let page: ClipFeedPage | null = null;
  if (feedUrl) {
    try {
      page = await fetchJson<ClipFeedPage>(feedUrl, { next: { revalidate: 60 } });
    } catch {
      page = null;
    }
  }

  return (
    <NextIntlClientProvider locale={locale} messages={{ clips: clipsMessages }}>
      {page ? (
        <ClipsFeed
          initialItems={page.items}
          initialCursor={page.next_cursor}
          apiBaseUrl={absoluteApiUrl("") ?? ""}
          locale={locale}
        />
      ) : (
        <FeedError />
      )}
    </NextIntlClientProvider>
  );
}
