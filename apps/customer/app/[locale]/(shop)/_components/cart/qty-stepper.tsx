"use client";

import { useCallback, useState } from "react";

export type QtyStepperLabels = {
  decrease: string;
  increase: string;
  value: string;
  updating: string;
  decreaseSymbol: string;
  increaseSymbol: string;
};

type QtyStepperProps = {
  value: number;
  min: number;
  max: number | null;
  disabled?: boolean;
  labels: QtyStepperLabels;
  onChange: (nextQty: number) => Promise<void>;
  "data-testid"?: string;
};

export function QtyStepper({
  value,
  min,
  max,
  disabled = false,
  labels,
  onChange,
  "data-testid": dataTestId = "cart-qty-stepper",
}: QtyStepperProps) {
  const [pending, setPending] = useState(false);
  const [displayQty, setDisplayQty] = useState(value);

  const syncValue = value;
  const shownQty = pending ? displayQty : syncValue;

  const atMin = shownQty <= min;
  const atMax = max !== null && shownQty >= max;

  const applyChange = useCallback(
    async (nextQty: number) => {
      const clamped = max === null ? Math.max(min, nextQty) : Math.min(Math.max(min, nextQty), max);
      if (clamped === syncValue) {
        return;
      }

      const previous = syncValue;
      setPending(true);
      setDisplayQty(clamped);

      try {
        await onChange(clamped);
      } catch {
        setDisplayQty(previous);
      } finally {
        setPending(false);
      }
    },
    [max, min, onChange, syncValue],
  );

  return (
    <div className="flex items-center gap-2" data-testid={dataTestId}>
      <button
        type="button"
        aria-label={labels.decrease}
        data-testid={`${dataTestId}-decrease`}
        disabled={disabled || pending || atMin}
        onClick={() => void applyChange(shownQty - 1)}
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-lg disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span aria-hidden>{labels.decreaseSymbol}</span>
      </button>
      <output
        data-testid={`${dataTestId}-value`}
        className="min-w-12 text-center font-mono text-lg"
        aria-live="polite"
        aria-busy={pending}
      >
        {shownQty}
      </output>
      <button
        type="button"
        aria-label={labels.increase}
        data-testid={`${dataTestId}-increase`}
        disabled={disabled || pending || atMax}
        onClick={() => void applyChange(shownQty + 1)}
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-lg disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span aria-hidden>{labels.increaseSymbol}</span>
      </button>
    </div>
  );
}
