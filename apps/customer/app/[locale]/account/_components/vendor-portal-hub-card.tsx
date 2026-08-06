"use client";

import { getRolesFromUser } from "@vergeo/auth/roles";
import { useSession } from "@vergeo/auth/use-session";

import { getVendorPortalUrl } from "../../(marketing)/sell/_components/vendor-app";

export type VendorPortalHubLabels = {
  title: string;
  body: string;
  cta: string;
};

type VendorPortalHubCardProps = {
  locale: string;
  labels: VendorPortalHubLabels;
};

export function VendorPortalHubCard({ locale, labels }: VendorPortalHubCardProps) {
  const { user, loading } = useSession();

  if (loading || !user) {
    return null;
  }

  const roles = getRolesFromUser(user);
  if (!roles.includes("vendor")) {
    return null;
  }

  const portalUrl = getVendorPortalUrl(locale);
  if (!portalUrl) {
    return null;
  }

  return (
    <article
      className="flex flex-col gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4 sm:col-span-2"
      data-testid="account-hub-vendor-portal"
    >
      <div className="space-y-1">
        <h3 className="font-medium text-display-ink">{labels.title}</h3>
        <p className="text-sm text-text-2">{labels.body}</p>
      </div>
      <a
        href={portalUrl}
        className="inline-flex min-h-11 w-fit items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        {labels.cta}
      </a>
    </article>
  );
}
