import Link from "next/link";

import { BranchDistance } from "./branch-distance";

export type OtherBranch = {
  slug: string;
  display_name: string;
  landmark: string | null;
  address?: string | null;
  lat?: number | null;
  lng?: number | null;
  hours?: Record<string, string>;
  open_now?: boolean | null;
  phone?: string | null;
  map_url?: string | null;
};

export type OtherBranchesLabels = {
  heading: string;
  aria: string;
  partOf: string;
  openNow: string;
  closedNow: string;
  hours: string;
  hoursLine: (day: string, hours: string) => string;
  phone: string;
  map: string;
  visit: (name: string) => string;
  kmAway: string;
  metresAway: string;
};

/**
 * "Other branches" on a shop page (multi-branch businesses): one card per
 * approved sibling shop. Server-rendered; the only client JS is the tiny
 * optional distance label.
 */
export function OtherBranches({
  locale,
  branches,
  labels,
}: {
  locale: string;
  branches: OtherBranch[];
  labels: OtherBranchesLabels;
}) {
  if (branches.length === 0) return null;
  return (
    <section
      aria-label={labels.aria}
      className="space-y-3 px-1 sm:px-4"
      data-testid="vendor-other-branches"
    >
      <div className="space-y-0.5">
        <h2 className="m-0 font-display text-h3 font-semibold text-display-ink">
          {labels.heading}
        </h2>
        <p className="m-0 text-sm text-text-2">{labels.partOf}</p>
      </div>
      <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {branches.map((branch) => {
          const hours = Object.entries(branch.hours ?? {});
          return (
            <li
              key={branch.slug}
              className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-1"
              data-testid="branch-card"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="m-0 text-base font-semibold text-text">
                  {branch.display_name}
                </h3>
                {branch.open_now === true ? (
                  <span className="rounded-pill bg-primary-tint px-2 py-0.5 text-xs font-semibold text-primary">
                    {labels.openNow}
                  </span>
                ) : branch.open_now === false ? (
                  <span className="rounded-pill bg-bg-2 px-2 py-0.5 text-xs font-semibold text-text-2">
                    {labels.closedNow}
                  </span>
                ) : null}
              </div>
              {branch.landmark || branch.address ? (
                <p className="m-0 text-sm text-text-2">
                  {[branch.landmark, branch.address]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              ) : null}
              {typeof branch.lat === "number" &&
              typeof branch.lng === "number" ? (
                <BranchDistance
                  lat={branch.lat}
                  lng={branch.lng}
                  kmTemplate={labels.kmAway}
                  metresTemplate={labels.metresAway}
                />
              ) : null}
              {hours.length > 0 ? (
                <details className="text-sm text-text-2">
                  <summary className="cursor-pointer text-text">
                    {labels.hours}
                  </summary>
                  <ul className="m-0 mt-1 list-none space-y-0.5 p-0">
                    {hours.map(([day, span]) => (
                      <li key={day}>{labels.hoursLine(day, span)}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
              {branch.phone ? (
                <p className="m-0 text-sm text-text">
                  <span className="text-text-2">{labels.phone} </span>
                  <span data-testid="branch-phone">{branch.phone}</span>
                </p>
              ) : null}
              <div className="mt-auto flex flex-wrap gap-2 pt-1">
                <Link
                  href={`/${locale}/v/${encodeURIComponent(branch.slug)}`}
                  className="inline-flex min-h-11 items-center rounded bg-primary px-3 text-sm font-semibold text-[var(--primary-btn-fg)] no-underline hover:bg-[var(--primary-btn-hover)]"
                >
                  {labels.visit(branch.display_name)}
                </Link>
                {branch.map_url ? (
                  <a
                    href={branch.map_url}
                    rel="noopener noreferrer"
                    target="_blank"
                    className="inline-flex min-h-11 items-center rounded border border-border px-3 text-sm text-text no-underline hover:border-primary"
                  >
                    {labels.map}
                  </a>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
