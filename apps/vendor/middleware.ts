import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import createMiddleware from "next-intl/middleware";

export default createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "always",
});

export const config = {
  matcher: ["/", "/(en|bem|nya|fr)/:path*"],
};
