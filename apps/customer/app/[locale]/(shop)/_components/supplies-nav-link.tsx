"use client";

import Link from "next/link";

import { useBusinessEligibility } from "./use-business-eligibility";

type SuppliesNavLinkProps = {
  locale: string;
  label: string;
};

/**
 * Desktop-header wholesale Supplies link, rendered only for verified business
 * buyers (eligibility resolved client-side — see useBusinessEligibility). Renders
 * an <li> so it slots straight into the header's nav list; nothing for everyone
 * else, so the common case adds no visible element.
 */
export function SuppliesNavLink({ locale, label }: SuppliesNavLinkProps) {
  const eligible = useBusinessEligibility();
  if (!eligible) {
    return null;
  }

  return (
    <li>
      <Link
        href={`/${locale}/supplies`}
        className="inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text"
      >
        {label}
      </Link>
    </li>
  );
}
