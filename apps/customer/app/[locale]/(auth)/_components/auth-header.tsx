"use client";

import { AppHeader } from "@vergeo/ui/src/app-header";
import Image from "next/image";
import Link from "next/link";

type AuthHeaderProps = {
  locale: string;
  appName: string;
  tagline: string;
  skipToContent: string;
  backToShopLabel: string;
  localeSwitcher?: React.ReactNode;
};

/** Auth-route header — brand-forward hero band with locale + back link. */
export function AuthHeader({
  locale,
  appName,
  tagline,
  skipToContent,
  backToShopLabel,
  localeSwitcher,
}: AuthHeaderProps) {
  return (
    <AppHeader
      variant="auth"
      data-testid="auth-header"
      appName={appName}
      tagline={tagline}
      skipLinkTargetId="auth-main"
      skipLinkLabel={skipToContent}
      navAriaLabel="Auth"
      localeSwitcher={localeSwitcher}
      secondaryLink={
        <Link
          href={`/${locale}`}
          className="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-panel-muted transition-colors hover:text-panel-text focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          <Image
            src="/icon-mark.png"
            alt=""
            width={22}
            height={22}
            className="h-5 w-5 object-contain"
            aria-hidden
          />
          {backToShopLabel}
        </Link>
      }
    />
  );
}
