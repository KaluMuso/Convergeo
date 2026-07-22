"use client";

import type { MomoRail } from "./step-payment";

type PaymentRailChoiceProps = {
  name: string;
  rail: MomoRail;
  label: string;
  checked: boolean;
  onChange: () => void;
};

const RAIL_BRAND_CLASS: Record<MomoRail, string> = {
  mtn: "bg-[var(--payment-rail-mtn)]",
  airtel: "bg-[var(--payment-rail-airtel)]",
};

/**
 * MoMo rail selector with operator brand colour swatch (design bundle fidelity).
 */
export function PaymentRailChoice({
  name,
  rail,
  label,
  checked,
  onChange,
}: PaymentRailChoiceProps) {
  const id = `${name}-${rail}`;

  return (
    <label
      htmlFor={id}
      className={[
        "flex min-h-11 cursor-pointer items-center gap-3 rounded-card border px-3 py-2 transition-[border-color,background-color] duration-fast ease-std",
        checked
          ? "border-primary bg-primary/5"
          : "border-border bg-surface hover:border-primary/40",
      ].join(" ")}
      data-testid={`payment-rail-${rail}`}
      data-selected={checked ? "true" : "false"}
    >
      <input
        id={id}
        type="radio"
        name={name}
        value={rail}
        checked={checked}
        onChange={onChange}
        className="sr-only"
      />
      <span
        className={[
          "size-3 shrink-0 rounded-full ring-1 ring-border/60",
          RAIL_BRAND_CLASS[rail],
        ].join(" ")}
        aria-hidden
      />
      <span className="font-body text-body text-text">{label}</span>
    </label>
  );
}
