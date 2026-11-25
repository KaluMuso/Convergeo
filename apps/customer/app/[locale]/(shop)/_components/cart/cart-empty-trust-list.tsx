"use client";

import { LcPackage, LcShieldCheck, LcTruck } from "@vergeo/ui/src/lucide-icons";

import { CustomerTrustStrip } from "@/components/customer-trust-strip";

export type CartEmptyTrustLabels = {
  escrow: string;
  delivery: string;
  pickup: string;
};

export function CartEmptyTrustList({
  labels,
  compact = false,
}: {
  labels: CartEmptyTrustLabels;
  compact?: boolean;
}) {
  const iconClass = "size-5";
  const items = [
    {
      id: "escrow",
      label: labels.escrow,
      hue: "green" as const,
      testId: "cart-trust-escrow",
      icon: <LcShieldCheck className={iconClass} duotone aria-hidden />,
    },
    {
      id: "delivery",
      label: labels.delivery,
      hue: "amber" as const,
      testId: "cart-trust-delivery",
      icon: <LcTruck className={iconClass} duotone aria-hidden />,
    },
    {
      id: "pickup",
      label: labels.pickup,
      hue: "teal" as const,
      testId: "cart-trust-pickup",
      icon: <LcPackage className={iconClass} duotone aria-hidden />,
    },
  ];

  return (
    <CustomerTrustStrip
      items={items}
      compact={compact}
      data-testid="cart-empty-trust-list"
      className={compact ? "border-0 bg-transparent px-0 py-0" : "mt-3"}
    />
  );
}
