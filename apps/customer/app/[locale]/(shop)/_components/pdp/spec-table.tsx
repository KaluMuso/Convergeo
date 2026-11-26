"use client";

import { useState, type HTMLAttributes } from "react";

import { formatSpecKey, type SpecGroup } from "./spec-groups";

export type PdpSpecTableProps = {
  groups: SpecGroup[];
  emptyLabel: string;
};

export function PdpSpecTable({ groups, emptyLabel }: PdpSpecTableProps) {
  const visible = groups.filter((group) => group.rows.length > 0);
  if (visible.length === 0) {
    return <p className="text-sm text-text-3">{emptyLabel}</p>;
  }

  return (
    <MotionSafeWrapper data-testid="pdp-spec-table" className="grid gap-4 md:grid-cols-2">
      {visible.map((group) => (
        <SpecGroupCard key={group.id} group={group} />
      ))}
    </MotionSafeWrapper>
  );
}

function SpecGroupCard({ group }: { group: SpecGroup }) {
  const [open, setOpen] = useState(true);
  return (
    <section className="overflow-hidden rounded border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-semibold text-text focus-visible:outline-none focus-visible:shadow-focusRing"
        aria-expanded={open}
      >
        {group.title}
        <span aria-hidden>{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <dl className="border-t border-border">
          {group.rows.map((row, index) => (
            <div
              key={row.key}
              className={[
                "grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3 px-3 py-2 text-sm",
                index % 2 === 0 ? "bg-bg" : "bg-bg-2",
              ].join(" ")}
            >
              <dt className="font-medium text-text-2">{formatSpecKey(row.key)}</dt>
              <dd className="whitespace-pre-wrap break-words text-text">{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

function MotionSafeWrapper({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={["motion-safe", className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </div>
  );
}
