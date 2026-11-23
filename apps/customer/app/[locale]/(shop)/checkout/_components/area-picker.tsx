"use client";

import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Radio } from "@vergeo/ui/src/radio";
import { useId, useMemo, useState } from "react";

import type { AddressType } from "../../../../../lib/delivery-estimate";

export type DeliveryArea = { slug: string; name: string; aliases: string[] };

export type AreaPickerLabels = {
  label: string;
  help: string;
  searchPlaceholder: string;
  noMatch: string;
  notListed: string;
  change: string;
  /** `{area}` */
  selectedTemplate: string;
  unavailable: string;
  typeLabel: string;
  home: string;
  work: string;
  workHelp: string;
};

const MAX_RESULTS = 8;

function normalise(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ'’]/g, "")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Areas whose name or alias contains every typed word; names starting with the query first. */
export function filterAreas(areas: DeliveryArea[], query: string): DeliveryArea[] {
  const words = normalise(query).split(" ").filter(Boolean);
  if (!words.length) return areas.slice(0, MAX_RESULTS);
  const scored: Array<{ area: DeliveryArea; rank: number }> = [];
  for (const area of areas) {
    const terms = [area.name, ...area.aliases].map(normalise);
    const hit = terms.find((term) => words.every((word) => term.includes(word)));
    if (hit === undefined) continue;
    const rank = terms.some((term) => term.startsWith(words.join(" "))) ? 0 : 1;
    scored.push({ area, rank });
  }
  return scored
    .sort((a, b) => a.rank - b.rank || a.area.name.localeCompare(b.area.name))
    .slice(0, MAX_RESULTS)
    .map((item) => item.area);
}

type AreaPickerProps = {
  areas: DeliveryArea[] | null;
  value: string | null;
  onChange: (slug: string | null) => void;
  addressType: AddressType;
  onAddressTypeChange: (type: AddressType) => void;
  labels: AreaPickerLabels;
};

/**
 * Searchable list of Lusaka areas plus Home / Work. Optional: when the buyer's
 * area is not listed (or the list fails to load), the typed landmark still
 * prices the delivery, so no option is ever taken away.
 */
export function AreaPicker({
  areas,
  value,
  onChange,
  addressType,
  onAddressTypeChange,
  labels,
}: AreaPickerProps) {
  const [query, setQuery] = useState("");
  const listId = useId();
  const typeName = useId();
  const selected = useMemo(
    () => (value && areas ? (areas.find((area) => area.slug === value) ?? null) : null),
    [areas, value],
  );
  const matches = useMemo(() => (areas ? filterAreas(areas, query) : []), [areas, query]);

  return (
    <div className="space-y-3" data-testid="checkout-area-picker">
      <fieldset className="space-y-1">
        <legend className="font-body text-sm font-semibold text-text">{labels.typeLabel}</legend>
        <div className="flex flex-wrap gap-x-6">
          <Radio
            name={typeName}
            label={labels.home}
            checked={addressType === "home"}
            onChange={() => onAddressTypeChange("home")}
          />
          <Radio
            name={typeName}
            label={labels.work}
            checked={addressType === "work"}
            onChange={() => onAddressTypeChange("work")}
          />
        </div>
        {addressType === "work" ? (
          <p className="font-body text-xs text-text-3">{labels.workHelp}</p>
        ) : null}
      </fieldset>

      {areas === null ? (
        <p className="font-body text-xs text-text-3">{labels.unavailable}</p>
      ) : selected ? (
        <div className="flex items-center justify-between gap-3 rounded-card border border-border bg-bg-2 px-4 py-3">
          <p className="font-body text-sm text-text" aria-live="polite">
            {labels.selectedTemplate.replace("{area}", selected.name)}
          </p>
          <button
            type="button"
            className="min-h-11 font-body text-sm text-primary underline"
            onClick={() => {
              onChange(null);
              setQuery("");
            }}
          >
            {labels.change}
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <FormField label={labels.label} helpText={labels.help}>
            <Input
              size="lg"
              value={query}
              placeholder={labels.searchPlaceholder}
              aria-controls={listId}
              autoComplete="off"
              onChange={(event) => setQuery(event.target.value)}
            />
          </FormField>
          <ul id={listId} className="flex flex-wrap gap-2" aria-label={labels.label}>
            {matches.map((area) => (
              <li key={area.slug}>
                <button
                  type="button"
                  className="min-h-11 rounded-full border border-border bg-surface px-4 font-body text-sm text-text"
                  onClick={() => onChange(area.slug)}
                >
                  {area.name}
                </button>
              </li>
            ))}
          </ul>
          <p className="font-body text-xs text-text-3">
            {matches.length === 0 ? labels.noMatch : labels.notListed}
          </p>
        </div>
      )}
    </div>
  );
}
