"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

export type CatalogSort = "relevance" | "cheapest" | "nearest" | "newest";

type SortBarLabels = {
  label: string;
  relevance: string;
  cheapest: string;
  nearest: string;
  newest: string;
};

type SortBarProps = {
  labels: SortBarLabels;
  value: CatalogSort;
  hasLocation: boolean;
};

export function SortBar({ labels, value, hasLocation }: SortBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const options = [
    { value: "relevance", label: labels.relevance },
    { value: "cheapest", label: labels.cheapest },
    { value: "nearest", label: labels.nearest, disabled: !hasLocation },
    { value: "newest", label: labels.newest },
  ];

  return (
    <div className="flex items-center justify-between gap-3">
      <label htmlFor="plp-sort" className="text-sm font-medium text-[var(--text-2)]">
        {labels.label}
      </label>
      <select
        id="plp-sort"
        value={value}
        disabled={isPending}
        className="min-w-[10rem]"
        onChange={(event) => {
          const next = event.target.value as CatalogSort;
          const params = new URLSearchParams(searchParams.toString());
          if (next === "relevance") {
            params.delete("sort");
          } else {
            params.set("sort", next);
          }
          params.delete("cursor");
          const query = params.toString();
          startTransition(() => {
            router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
          });
        }}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
