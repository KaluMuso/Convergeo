"use client";

import { useId } from "react";

import type { DetailEntry } from "./canonical-details";

export type CanonicalDetailsLabels = {
  about: string;
  heading: string;
  help: string;
  name: string;
  value: string;
  add: string;
  remove: string;
  invalid: string;
};
export function CanonicalDetailsFields({
  description,
  entries,
  onDescription,
  onEntries,
  labels,
}: {
  description: string;
  entries: DetailEntry[];
  onDescription: (value: string) => void;
  onEntries: (value: DetailEntry[]) => void;
  labels: CanonicalDetailsLabels;
}) {
  const id = useId();
  return (
    <fieldset className="flex min-w-0 flex-col gap-3">
      <legend className="font-medium">{labels.heading}</legend>
      <p id={`${id}-help`} className="text-sm text-text-2">
        {labels.help}
      </p>
      <label className="flex flex-col gap-1">
        {labels.about}
        <textarea
          value={description}
          onChange={(event) => onDescription(event.target.value)}
          maxLength={5000}
          rows={4}
          aria-describedby={`${id}-help`}
          className="w-full rounded border border-border p-2"
        />
      </label>
      {entries.map((entry, index) => (
        <div key={index} className="grid min-w-0 gap-2 sm:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-1">
            {labels.name} {index + 1}
            <input
              value={entry.name}
              maxLength={80}
              onChange={(event) =>
                onEntries(
                  entries.map((row, i) =>
                    i === index ? { ...row, name: event.target.value } : row,
                  ),
                )
              }
              className="min-w-0 rounded border border-border p-2"
            />
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            {labels.value} {index + 1}
            <textarea
              value={entry.value}
              maxLength={2000}
              rows={2}
              onChange={(event) =>
                onEntries(
                  entries.map((row, i) =>
                    i === index ? { ...row, value: event.target.value } : row,
                  ),
                )
              }
              className="min-w-0 rounded border border-border p-2"
            />
          </label>
          <button
            type="button"
            onClick={() => onEntries(entries.filter((_, i) => i !== index))}
            aria-label={`${labels.remove} ${index + 1}`}
            className="min-h-11 justify-self-start px-2 text-sm"
          >
            {labels.remove}
          </button>
        </div>
      ))}
      <button
        type="button"
        disabled={entries.length >= 32}
        onClick={() => onEntries([...entries, { name: "", value: "" }])}
        className="min-h-11 self-start rounded border border-border px-3 disabled:opacity-50"
      >
        {labels.add}
      </button>
    </fieldset>
  );
}
