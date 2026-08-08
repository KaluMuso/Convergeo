"use client";

import { PUBLIC_LOCALES } from "@vergeo/i18n";
import { usePathname } from "next/navigation";

import { swapLocaleInPath } from "../../../../lib/locale-path";

export type TopUtilityBarLabels = {
  ariaLabel: string;
  countryCode: string;
  localeAria: string;
  localeNames: Record<string, string>;
  phone: string;
  email: string;
  socialAria: string;
  facebookAria: string;
  twitterAria: string;
  instagramAria: string;
  emailAria: string;
};

export type TopUtilityBarLinks = {
  phoneHref: string;
  emailHref: string;
  facebook: string;
  twitter: string;
  instagram: string;
};

type TopUtilityBarProps = {
  locale: string;
  labels: TopUtilityBarLabels;
  links: TopUtilityBarLinks;
};

function ZambiaFlag({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 36 24" className={className} aria-hidden focusable="false" role="img">
      <rect width="36" height="24" fill="#198A00" />
      <rect x="24" width="4" height="24" fill="#000" />
      <rect x="28" width="4" height="24" fill="#EF7D00" />
      <rect x="32" width="4" height="24" fill="#DE2010" />
      <circle cx="10" cy="8" r="3.2" fill="#EF7D00" />
      <path
        d="M7.2 11.2c.6 2.2 2.2 3.6 2.8 3.6s2.2-1.4 2.8-3.6c-1.1.7-2 .9-2.8.9s-1.7-.2-2.8-.9z"
        fill="#000"
      />
    </svg>
  );
}

function SocialIcon({ kind }: { kind: "facebook" | "twitter" | "instagram" | "mail" }) {
  const common = "h-3.5 w-3.5";
  if (kind === "facebook") {
    return (
      <svg viewBox="0 0 24 24" className={common} aria-hidden fill="currentColor">
        <path d="M14 8h3V5h-3c-2.2 0-4 1.8-4 4v2H7v3h3v7h3v-7h3l1-3h-4V9c0-.6.4-1 1-1z" />
      </svg>
    );
  }
  if (kind === "twitter") {
    return (
      <svg viewBox="0 0 24 24" className={common} aria-hidden fill="currentColor">
        <path d="M18.2 3H21l-6.5 7.4L22 21h-6.2l-4.3-5.5L6.2 21H3.4l7-8L2.2 3h6.3l3.9 5.1L18.2 3zm-1.1 16.2h1.7L7 4.7H5.2l11.9 14.5z" />
      </svg>
    );
  }
  if (kind === "instagram") {
    return (
      <svg viewBox="0 0 24 24" className={common} aria-hidden fill="currentColor">
        <path d="M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4zm0 2a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H7zm5 2.5A4.5 4.5 0 1 1 7.5 12 4.5 4.5 0 0 1 12 7.5zm0 2A2.5 2.5 0 1 0 14.5 12 2.5 2.5 0 0 0 12 9.5zM17.8 6.6a1 1 0 1 1-1 1 1 1 0 0 1 1-1z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className={common} aria-hidden fill="currentColor">
      <path d="M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zm8 6.5L4.8 7.6l-.6.8L12 14.2l7.8-5.8-.6-.8L12 12.5z" />
    </svg>
  );
}

/**
 * Thin utility strip: Zambia + language, contact, socials (legacy Convergeo chrome).
 */
export function TopUtilityBar({ locale, labels, links }: TopUtilityBarProps) {
  const pathname = usePathname();

  const handleLocaleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextLocale = event.target.value;
    if (nextLocale === locale) {
      return;
    }
    const nextPath = swapLocaleInPath(pathname, nextLocale);
    const query = window.location.search;
    window.location.assign(query ? `${nextPath}${query}` : nextPath);
  };

  const socialClass =
    "inline-flex h-8 w-8 items-center justify-center rounded-sm text-panel-muted transition-colors duration-fast ease-std hover:bg-white/10 hover:text-panel-text focus-visible:outline-none focus-visible:shadow-focusRing";

  return (
    <div
      data-testid="top-utility-bar"
      role="region"
      aria-label={labels.ariaLabel}
      className="border-b border-panel-border bg-panel text-panel-text"
    >
      <div className="mx-auto flex min-h-9 max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-1 text-micro lg:px-6">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <span className="inline-flex items-center gap-1.5 font-medium tracking-wide">
            <ZambiaFlag className="h-3.5 w-5 shrink-0 rounded-[1px] shadow-sm" />
            <span className="hidden text-panel-muted xs:inline sm:inline">
              {labels.countryCode}
            </span>
          </span>
          <label className="inline-flex items-center gap-1.5 text-panel-muted">
            <span className="sr-only">{labels.localeAria}</span>
            <select
              value={locale}
              onChange={handleLocaleChange}
              aria-label={labels.localeAria}
              data-testid="top-utility-locale"
              className="max-w-[7.5rem] cursor-pointer truncate border-0 bg-transparent py-1 pr-1 font-medium text-panel-text focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {PUBLIC_LOCALES.map((code) => (
                <option key={code} value={code} className="bg-panel text-panel-text">
                  {code} · {labels.localeNames[code] ?? code}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="hidden min-w-0 items-center gap-4 text-panel-muted md:flex">
          <a
            href={links.phoneHref}
            className="truncate transition-colors hover:text-panel-text focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            {labels.phone}
          </a>
          <a
            href={links.emailHref}
            className="truncate transition-colors hover:text-panel-text focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            {labels.email}
          </a>
        </div>

        <nav aria-label={labels.socialAria} className="flex shrink-0 items-center gap-0.5">
          <a
            href={links.facebook}
            className={socialClass}
            aria-label={labels.facebookAria}
            rel="noopener noreferrer"
            target="_blank"
          >
            <SocialIcon kind="facebook" />
          </a>
          <a
            href={links.twitter}
            className={socialClass}
            aria-label={labels.twitterAria}
            rel="noopener noreferrer"
            target="_blank"
          >
            <SocialIcon kind="twitter" />
          </a>
          <a
            href={links.instagram}
            className={socialClass}
            aria-label={labels.instagramAria}
            rel="noopener noreferrer"
            target="_blank"
          >
            <SocialIcon kind="instagram" />
          </a>
          <a href={links.emailHref} className={socialClass} aria-label={labels.emailAria}>
            <SocialIcon kind="mail" />
          </a>
        </nav>
      </div>
    </div>
  );
}
