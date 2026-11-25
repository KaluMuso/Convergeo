/**
 * Slim post-hero trust strip for the customer homepage. COD-only pilot:
 * copy never mentions escrow, mobile money or cards (see docs/plan decisions).
 */

import { LcRefreshCw, LcShieldCheck, LcTruck, LcWallet } from "@vergeo/ui/src/lucide-icons";

import { CustomerTrustStrip, type CustomerTrustStripItem } from "@/components/customer-trust-strip";

export type HomeTrustStripLabels = {
  ariaLabel: string;
  cod: string;
  verified: string;
  lusaka: string;
  returns: string;
};

type HomeTrustStripProps = {
  labels: HomeTrustStripLabels;
};

const ICON_CLASS = "size-5";

export function HomeTrustStrip({ labels }: HomeTrustStripProps) {
  const items: CustomerTrustStripItem[] = [
    {
      id: "cod",
      label: labels.cod,
      hue: "green",
      testId: "home-trust-cod",
      icon: <LcWallet className={ICON_CLASS} duotone aria-hidden />,
    },
    {
      id: "verified",
      label: labels.verified,
      hue: "blue",
      testId: "home-trust-verified",
      icon: <LcShieldCheck className={ICON_CLASS} duotone aria-hidden />,
    },
    {
      id: "lusaka",
      label: labels.lusaka,
      hue: "amber",
      testId: "home-trust-lusaka",
      icon: <LcTruck className={ICON_CLASS} duotone aria-hidden />,
    },
    {
      id: "returns",
      label: labels.returns,
      hue: "teal",
      testId: "home-trust-returns",
      icon: <LcRefreshCw className={ICON_CLASS} duotone aria-hidden />,
    },
  ];

  return (
    <CustomerTrustStrip ariaLabel={labels.ariaLabel} items={items} data-testid="home-trust-strip" />
  );
}
