"use client";

import { useState, type HTMLAttributes } from "react";

import type { SpecRow } from "./specs-table";

export type SpecGroup = {
  id: string;
  title: string;
  rows: SpecRow[];
};

export type PdpSpecTableProps = {
  groups: SpecGroup[];
  emptyLabel: string;
};

export function groupSpecRows(rows: SpecRow[], groupTitles: Record<string, string>): SpecGroup[] {
  const buckets = new Map<string, SpecRow[]>();
  const ungrouped: SpecRow[] = [];

  for (const row of rows) {
    const slash = row.key.indexOf("/");
    const dot = row.key.indexOf(".");
    const splitAt = slash > 0 ? slash : dot > 0 ? dot : -1;
    if (splitAt > 0) {
      const groupKey = row.key.slice(0, splitAt);
      const rest = row.key.slice(splitAt + 1);
      const list = buckets.get(groupKey) ?? [];
      list.push({ key: rest, value: row.value });
      buckets.set(groupKey, list);
    } else {
      ungrouped.push(row);
    }
  }

  const groups: SpecGroup[] = [];
  for (const [id, groupRows] of buckets) {
    if (groupRows.length === 0) {
      continue;
    }
    groups.push({
      id,
      title: groupTitles[id] ?? formatSpecKey(id),
      rows: groupRows,
    });
  }
  if (ungrouped.length > 0) {
    groups.push({
      id: "details",
      title: groupTitles.details ?? "Item details",
      rows: ungrouped,
    });
  }
  return groups;
}

function formatSpecKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

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
