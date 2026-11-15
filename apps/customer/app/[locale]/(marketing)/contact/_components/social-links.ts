/**
 * Public social profile URLs, resolved from env. There are no built-in defaults:
 * until an official profile exists the matching icon is hidden, rather than linking
 * to the generic facebook.com / x.com / instagram.com home pages.
 *
 * Direct `process.env.NEXT_PUBLIC_*` member access so Next inlines the values.
 */
export type SocialLinks = {
  facebook: string | null;
  twitter: string | null;
  instagram: string | null;
};

/** `https://` URL with a real path or subdomain, or `null` (empty / malformed / http). */
export function normaliseSocialUrl(raw: string | undefined): string | null {
  const trimmed = raw?.trim();
  if (!trimmed) {
    return null;
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") {
    return null;
  }
  // A bare host ("https://www.facebook.com/") is the generic homepage, not a profile.
  if (parsed.pathname.replace(/\/+$/, "") === "" && !parsed.search) {
    return null;
  }
  return parsed.toString();
}

export function getSocialLinks(): SocialLinks {
  return {
    facebook: normaliseSocialUrl(process.env.NEXT_PUBLIC_SOCIAL_FACEBOOK_URL),
    twitter: normaliseSocialUrl(process.env.NEXT_PUBLIC_SOCIAL_TWITTER_URL),
    instagram: normaliseSocialUrl(process.env.NEXT_PUBLIC_SOCIAL_INSTAGRAM_URL),
  };
}
