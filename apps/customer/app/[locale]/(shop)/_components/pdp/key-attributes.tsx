"use client";

import { useState } from "react";

export type KeyAttributeRow = {
  key: string;
  value: string;
};

export type KeyAttributesProps = {
  rows: KeyAttributeRow[];
  seeMoreLabel: string;
  specsSectionId: string;
};

export function KeyAttributes({ rows, seeMoreLabel, specsSectionId }: KeyAttributesProps) {
  const [collapsed, setCollapsed] = useState(true);
  const preview = rows.slice(0, 5);
  if (preview.length === 0) {
    return null;
  }

  const scrollToSpecs = () => {
    document.getElementById(specsSectionId)?.scrollIntoView({ behavior: "smooth" });
    setCollapsed(false);
  };

  return (
    <section data-testid="pdp-key-attributes" className="flex flex-col gap-2">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {preview.map((row) => (
          <div key={row.key} className="contents">
            <dt className="font-semibold text-text">{row.key}</dt>
            <dd className="text-text-2">{row.value}</dd>
          </div>
        ))}
      </dl>
      {rows.length > preview.length ? (
        <button
          type="button"
          onClick={scrollToSpecs}
          className="w-fit text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {seeMoreLabel}
        </button>
      ) : null}
      {!collapsed && rows.length > preview.length ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-border pt-2 text-sm">
          {rows.slice(5).map((row) => (
            <div key={row.key} className="contents">
              <dt className="font-semibold text-text">{row.key}</dt>
              <dd className="text-text-2">{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}
