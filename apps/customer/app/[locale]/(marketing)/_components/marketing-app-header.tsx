import { AppHeader } from "@vergeo/ui/src/app-header";
import Link from "next/link";

import { BrandLogo } from "../../(shop)/_components/brand-logo";

import { MarketingSignInSlot } from "./marketing-sign-in-slot";

export type MarketingAppHeaderLabels = {
  appName: string;
  navAriaLabel: string;
  about: string;
  contact: string;
  help: string;
  sell: string;
  signIn: string;
  account: string;
};

type MarketingAppHeaderProps = {
  locale: string;
  labels: MarketingAppHeaderLabels;
};

export function MarketingAppHeader({ locale, labels }: MarketingAppHeaderProps) {
  const navLinks = [
    { key: "about", href: `/${locale}/about`, label: labels.about },
    { key: "contact", href: `/${locale}/contact`, label: labels.contact },
    { key: "help", href: `/${locale}/help`, label: labels.help },
    { key: "sell", href: `/${locale}/sell`, label: labels.sell },
  ];

  return (
    <AppHeader
      variant="marketing"
      features={{ showSearch: false, showLocale: false }}
      appName={labels.appName}
      logo={
        <Link
          href={`/${locale}`}
          className="inline-flex items-center transition-opacity duration-fast ease-std hover:opacity-90"
          aria-label={labels.appName}
        >
          <BrandLogo appName={labels.appName} />
        </Link>
      }
      navAriaLabel={labels.navAriaLabel}
      skipLinkTargetId="marketing-main"
      navLinks={navLinks}
      signInSlot={
        <MarketingSignInSlot
          locale={locale}
          signInLabel={labels.signIn}
          accountLabel={labels.account}
        />
      }
      LinkComponent={Link}
    />
  );
}
