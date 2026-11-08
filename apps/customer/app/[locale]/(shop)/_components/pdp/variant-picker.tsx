"use client";

import { useTranslations } from "next-intl";
import { useCallback, useId, useRef, type KeyboardEvent } from "react";

import {
  valueAvailability,
  type ListingVariantOption,
  type VariantOptionGroup,
  type VariantSelection,
} from "./variant-selection";

export type VariantPickerProps = {
  groups: VariantOptionGroup[];
  variants: ListingVariantOption[];
  selection: VariantSelection;
  onSelect: (groupId: string, valueId: string) => void;
  /** Highlight unpicked groups after a blocked add-to-cart. */
  showMissing?: boolean;
};

/**
 * Colour swatches and size pills. Each group is a radiogroup with roving focus
 * (arrow keys move, Space/Enter picks); sold-out and unoffered combinations stay
 * visible but disabled, with the reason in their accessible name.
 */
export function VariantPicker({
  groups,
  variants,
  selection,
  onSelect,
  showMissing = false,
}: VariantPickerProps) {
  const t = useTranslations("catalog");
  const baseId = useId();
  const groupRefs = useRef(new Map<string, HTMLDivElement>());

  const onKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>, groupId: string) => {
    if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"].includes(event.key)) {
      return;
    }
    const container = groupRefs.current.get(groupId);
    const radios = Array.from(
      container?.querySelectorAll<HTMLButtonElement>('[role="radio"]:not([disabled])') ?? [],
    );
    if (radios.length === 0) {
      return;
    }
    event.preventDefault();
    const current = radios.indexOf(document.activeElement as HTMLButtonElement);
    let next = current;
    if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = radios.length - 1;
    } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      next = current < 0 ? 0 : (current + 1) % radios.length;
    } else {
      next = current <= 0 ? radios.length - 1 : current - 1;
    }
    radios[next]?.focus();
  }, []);

  return (
    <div className="flex flex-col gap-4" data-testid="pdp-variant-picker">
      {groups.map((group) => {
        const labelId = `${baseId}-${group.id}`;
        const chosen = group.values.find((value) => value.id === selection[group.id]);
        const missing = showMissing && !chosen;
        const firstEnabled = group.values.find(
          (value) =>
            valueAvailability(groups, variants, selection, group.id, value.id) === "available",
        );
        const tabStop = chosen?.id ?? firstEnabled?.id;
        return (
          <div key={group.id} className="flex flex-col gap-2">
            <p id={labelId} className="text-sm font-medium text-text">
              {chosen
                ? t("pdp.variants.groupLabel", { group: group.name, value: chosen.label })
                : t("pdp.variants.choose", { group: group.name })}
            </p>
            <div
              ref={(node) => {
                if (node) {
                  groupRefs.current.set(group.id, node);
                } else {
                  groupRefs.current.delete(group.id);
                }
              }}
              role="radiogroup"
              aria-labelledby={labelId}
              aria-required="true"
              aria-invalid={missing || undefined}
              data-testid={`pdp-variant-group-${group.id}`}
              onKeyDown={(event) => onKeyDown(event, group.id)}
              className={[
                "flex flex-wrap gap-2 rounded",
                missing ? "outline outline-2 outline-offset-4 outline-danger" : "",
              ].join(" ")}
            >
              {group.values.map((value) => {
                const availability = valueAvailability(
                  groups,
                  variants,
                  selection,
                  group.id,
                  value.id,
                );
                const checked = selection[group.id] === value.id;
                const disabled = availability !== "available" && !checked;
                const accessibleName =
                  availability === "soldOut"
                    ? t("pdp.variants.soldOut", { value: value.label })
                    : availability === "unavailable"
                      ? t("pdp.variants.unavailable", { value: value.label })
                      : value.label;
                const swatch = group.display === "swatch" && value.swatchHex;
                return (
                  <button
                    key={value.id}
                    type="button"
                    role="radio"
                    aria-checked={checked}
                    aria-label={accessibleName}
                    title={accessibleName}
                    disabled={disabled}
                    tabIndex={value.id === tabStop ? 0 : -1}
                    data-testid={`pdp-variant-value-${value.id}`}
                    data-availability={availability}
                    onClick={() => onSelect(group.id, value.id)}
                    className={[
                      "relative inline-flex min-h-11 items-center justify-center border text-sm font-medium",
                      "focus-visible:outline-none focus-visible:shadow-focusRing",
                      "disabled:cursor-not-allowed disabled:opacity-50",
                      swatch ? "min-w-11 rounded-full p-1" : "min-w-11 rounded px-3",
                      checked
                        ? "border-primary bg-primary/5 ring-2 ring-primary"
                        : "border-border bg-bg text-text",
                    ].join(" ")}
                  >
                    {swatch ? (
                      <span
                        aria-hidden="true"
                        className="block h-8 w-8 rounded-full border border-border"
                        style={{ backgroundColor: value.swatchHex ?? undefined }}
                      />
                    ) : (
                      <span aria-hidden="true">{value.label}</span>
                    )}
                    {availability === "soldOut" ? (
                      <span
                        aria-hidden="true"
                        className="pointer-events-none absolute inset-x-1 top-1/2 h-px -rotate-12 bg-text-2"
                      />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
