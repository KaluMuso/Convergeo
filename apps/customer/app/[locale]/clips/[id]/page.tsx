import { LOCALES, formatK, loadNamespace, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { absoluteApiUrl } from "../../../../lib/api-base-url";
import { fetchJson } from "../../../../lib/fetch-json";

import type { Clip } from "../_components/types";
import type { Metadata } from "next";

/**
 * M17-P08 — the public, shareable clip page.
 *
 * This is the WhatsApp deep-link surface, and it is deliberately the *opposite*
 * of the feed: fully server-rendered, no feed JS, and **poster-only**. A share
 * must never force a video download — someone tapping a link in a group chat has
 * not consented to spending 4 MB, on any connection. The video is behind an
 * explicit tap, exactly like the feed, but here even the player is a plain
 * `<video preload="none">` with no autoplay path at all.
 *
 * Unlike the feed route, this page IS indexable: it is the one clip surface with
 * index-worthy content (a real product, a real vendor, a real price) and the OG
 * tags that make a shared link look like something worth opening.
 *
 * Published-only. A taken-down clip 404s on the next request, because the API
 * refuses it — there is no cache in front of this to purge.
 */

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

async function loadClip(id: string): Promise<Clip | null> {
  const url = absoluteApiUrl(`/clips/${encodeURIComponent(id)}`);
  if (!url) {
    return null;
  }
  try {
    return await fetchJson<Clip>(url, { next: { revalidate: 60 } });
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, id } = await params;
  const clip = await loadClip(id);
  const messages = (await loadNamespace(locale as Locale, "clips")) as {
    share: { title: string; description: string };
  };
  if (!clip) {
    return { robots: { index: false, follow: false } };
  }

  const vendor = clip.vendor.display_name ?? "";
  const title = messages.share.title.replace("{vendor}", vendor);
  const description = clip.caption ?? messages.share.description;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "video.other",
      images: clip.poster_url ? [{ url: clip.poster_url }] : undefined,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: clip.poster_url ? [clip.poster_url] : undefined,
    },
  };
}

export default async function SharedClipPage({ params }: PageProps) {
  const { locale, id } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);

  const clip = await loadClip(id);
  if (!clip) {
    notFound();
  }

  const t = await getTranslations("clips");
  const vendor = clip.vendor.display_name ?? "";
  // Prefer the small rendition: a shared link is the least-consented context
  // there is, so the cheaper file is the honest default.
  const rendition = clip.renditions["480p"] ?? Object.values(clip.renditions)[0] ?? null;

  return (
    <main className="mx-auto flex w-full max-w-lg flex-col gap-4 p-4">
      <h1 className="text-h2 font-semibold text-text">{t("feed.byVendor", { vendor })}</h1>

      {/* preload="none" and no autoplay: the poster is all that loads until a tap. */}
      <video
        data-testid="shared-clip-video"
        poster={clip.poster_url ?? undefined}
        src={rendition?.url}
        controls
        preload="none"
        playsInline
        className="w-full rounded-2 bg-bg-2"
      >
        <track kind="captions" />
      </video>

      {clip.caption ? <p className="text-sm text-text">{clip.caption}</p> : null}

      {clip.listings.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-h3 font-semibold text-text">{t("overlay.title")}</h2>
          <ul className="flex flex-col gap-2">
            {clip.listings.map((listing) => (
              <li
                key={listing.listing_id}
                className="flex items-center justify-between gap-2 rounded-2 border border-border p-3"
              >
                <span className="text-sm text-text">{listing.title ?? ""}</span>
                <span className="text-sm text-price">
                  {formatK(listing.price_ngwee, { locale })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
