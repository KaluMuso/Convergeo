"use client";

import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";

import { useSession } from "../../../../lib/customer-session";

type MarketingSignInSlotProps = {
  locale: string;
  signInLabel: string;
  accountLabel: string;
};

/**
 * Session-aware header action for the marketing pages. Server render and the
 * first client paint show "Sign in" (the safe default for guests and for the
 * static HTML); once the browser session is known a signed-in visitor sees a
 * link to their account instead.
 */
export function MarketingSignInSlot({
  locale,
  signInLabel,
  accountLabel,
}: MarketingSignInSlotProps) {
  const { session } = useSession();
  const signedIn = Boolean(session);

  return (
    <LinkButton
      href={signedIn ? `/${locale}/account` : `/${locale}/login`}
      variant="primary"
      size="md"
      LinkComponent={Link}
    >
      {signedIn ? accountLabel : signInLabel}
    </LinkButton>
  );
}
