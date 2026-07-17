import { mergeSessionCookies, updateSession } from "@vergeo/auth/middleware";
import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { type NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";

const intlMiddleware = createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "always",
});

export default async function middleware(request: NextRequest) {
  const session = await updateSession(request);
  const localeResponse = intlMiddleware(request);
  return mergeSessionCookies(session.response, localeResponse);
}

export const config = {
  matcher: ["/", "/(en|bem|nya|fr|zh)/:path*"],
};
