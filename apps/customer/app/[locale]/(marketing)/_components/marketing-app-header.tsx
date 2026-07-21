import { AppHeader } from "@vergeo/ui/src/app-header";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";

export type MarketingAppHeaderLabels = {
  appName: string;
  navAriaLabel: string;
  about: string;
  contact: string;
  help: string;
  sell: string;
  signIn: string;
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
      features={{ showSearch: false }}
      appName={labels.appName}
      logo={
        <Link href={`/${locale}`} className="font-display text-primary">
          {labels.appName}
        </Link>
      }
      navAriaLabel={labels.navAriaLabel}
      skipLinkTargetId="marketing-main"
      navLinks={navLinks}
      signInSlot={
        <LinkButton href={`/${locale}/login`} variant="primary" size="md" LinkComponent={Link}>
          {labels.signIn}
        </LinkButton>
      }
      LinkComponent={Link}
    />
  );
}
