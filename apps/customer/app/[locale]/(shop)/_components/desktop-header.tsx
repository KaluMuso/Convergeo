import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import Link from "next/link";

type DesktopHeaderLabels = {
  appName: string;
  navAriaLabel: string;
  searchPlaceholder: string;
  browse: string;
  services: string;
  events: string;
  askVergeo: string;
  account: string;
  cart: string;
  themeLabel: string;
  themeLight: string;
  themeDark: string;
  themeSystem: string;
};

type DesktopHeaderProps = {
  locale: string;
  labels: DesktopHeaderLabels;
};

/**
 * Desktop-only (lg+) shop header — logo · search · primary nav · account/cart/theme.
 * Mobile (<1024px) keeps the existing TopNav untouched; this header is `hidden`
 * below the lg breakpoint. Sticky, token-driven (bg-surface / border-border),
 * structure inherited from the committed design's Nav (docs/designs, SELECTION §3).
 */
export function DesktopHeader({ locale, labels }: DesktopHeaderProps) {
  const navLinks = [
    { key: "browse", href: `/${locale}/search`, label: labels.browse },
    { key: "services", href: `/${locale}/services`, label: labels.services },
    { key: "events", href: `/${locale}/events`, label: labels.events },
    { key: "ask", href: `/${locale}/ask`, label: labels.askVergeo },
  ];

  return (
    <header className="sticky top-0 z-50 hidden border-b border-border bg-surface shadow-1 lg:block">
      <nav
        aria-label={labels.navAriaLabel}
        className="mx-auto flex h-16 w-full max-w-7xl items-center gap-6 px-6"
      >
        <Link
          href={`/${locale}`}
          className="shrink-0 font-display text-2xl leading-none text-primary"
        >
          {labels.appName}
        </Link>

        <Link
          href={`/${locale}/search`}
          className="flex h-11 min-w-0 max-w-xl flex-1 items-center rounded-pill border border-border bg-bg px-4 text-sm text-text-3"
        >
          {labels.searchPlaceholder}
        </Link>

        <ul className="flex shrink-0 list-none items-center gap-1 p-0">
          {navLinks.map((link) => (
            <li key={link.key}>
              <Link
                href={link.href}
                className="inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <ThemeToggle
            label={labels.themeLabel}
            lightLabel={labels.themeLight}
            darkLabel={labels.themeDark}
            systemLabel={labels.themeSystem}
          />
          <Link
            href={`/${locale}/account`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text"
          >
            <span aria-hidden className="text-base leading-none">
              {"\u{1F464}"}
            </span>
            {labels.account}
          </Link>
          <Link
            href={`/${locale}/cart`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text"
          >
            <span aria-hidden className="text-base leading-none">
              {"\u{1F6D2}"}
            </span>
            {labels.cart}
          </Link>
        </div>
      </nav>
    </header>
  );
}
