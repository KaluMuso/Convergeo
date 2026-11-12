"use client";

import { barPercent } from "./analytics-data";

export type BarItem = { key: string; label: string; value: number; display: string };

type BarListProps = {
  items: BarItem[];
  caption: string;
  emptyLabel: string;
  labelHeader: string;
  valueHeader: string;
};

/**
 * Accessible CSS bar chart (no chart library, plan 1B-05): a real table, so screen
 * readers get the label and value; the bar is decorative.
 */
export function BarList({ items, caption, emptyLabel, labelHeader, valueHeader }: BarListProps) {
  if (items.length === 0) {
    return <p className="text-sm text-muted">{emptyLabel}</p>;
  }
  const max = Math.max(...items.map((item) => item.value));
  return (
    <table className="w-full table-fixed text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">{labelHeader}</th>
          <th scope="col">{valueHeader}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.key} className="align-middle">
            <th
              scope="row"
              className="w-2/5 truncate py-1 pr-2 text-left font-normal text-text"
              title={item.label}
            >
              {item.label}
            </th>
            <td className="py-1">
              <div className="flex items-center gap-2">
                <div className="h-2 flex-1 rounded-full bg-bg" aria-hidden="true">
                  <div
                    className="h-2 rounded-full bg-primary"
                    style={{ width: `${barPercent(item.value, max)}%` }}
                  />
                </div>
                <span className="w-20 shrink-0 text-right font-mono text-xs text-muted">
                  {item.display}
                </span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
