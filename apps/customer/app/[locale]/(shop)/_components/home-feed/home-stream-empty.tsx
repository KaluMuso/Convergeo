import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";

import { getVendorSignupUrl } from "../../../(marketing)/sell/_components/vendor-app";

export type HomeStreamEmptyLabels = {
  title: string;
  body: string;
  cta: string;
};

export function HomeStreamEmpty({
  locale,
  labels,
}: {
  locale: string;
  labels: HomeStreamEmptyLabels;
}) {
  const vendorSignup = getVendorSignupUrl(locale);
  const ctaHref = vendorSignup ?? `/${locale}/sell`;

  return (
    <div
      className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-bg-2 px-4 py-8 text-center sm:py-10"
      data-testid="home-stream-empty"
    >
      <p className="m-0 font-display text-h3 font-bold text-display-ink">{labels.title}</p>
      <p className="m-0 max-w-sm text-sm text-text-2">{labels.body}</p>
      <LinkButton
        href={ctaHref}
        variant="primary"
        className="mt-1 rounded-pill px-6 text-sm font-semibold"
        LinkComponent={vendorSignup ? undefined : Link}
        {...(vendorSignup ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      >
        {labels.cta}
      </LinkButton>
    </div>
  );
}
