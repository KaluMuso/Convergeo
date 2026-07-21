"use client";

import { Button } from "@vergeo/ui/src/button";
import { Input } from "@vergeo/ui/src/input";
import { Select } from "@vergeo/ui/src/select";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState, useTransition } from "react";

import { encodeSearchFilters, type SearchFilterState } from "./search-filters";

export type SearchCategoryOption = {
  path: string;
  label: string;
};

export type SearchFilterPanelLabels = {
  heading: string;
  price: string;
  minPrice: string;
  maxPrice: string;
  category: string;
  categoryAll: string;
  apply: string;
  clear: string;
};

type SearchFilterPanelProps = {
  labels: SearchFilterPanelLabels;
  categories: SearchCategoryOption[];
  initialState: SearchFilterState;
  className?: string;
  onApplied?: () => void;
};

function mergeSearchParams(current: URLSearchParams, filters: SearchFilterState): URLSearchParams {
  const next = new URLSearchParams(current.toString());
  next.delete("page");
  next.delete("min_price");
  next.delete("max_price");
  next.delete("category_path");

  const encoded = encodeSearchFilters(filters);
  for (const [key, value] of encoded.entries()) {
    next.set(key, value);
  }

  return next;
}

export function SearchFilterPanel({
  labels,
  categories,
  initialState,
  className,
  onApplied,
}: SearchFilterPanelProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [state, setState] = useState<SearchFilterState>(initialState);

  const pushFilters = useCallback(
    (next: SearchFilterState) => {
      const params = mergeSearchParams(searchParams, next);
      const query = params.toString();
      startTransition(() => {
        router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
        onApplied?.();
      });
    },
    [onApplied, pathname, router, searchParams, startTransition],
  );

  return (
    <aside
      className={[
        "flex flex-col gap-4 rounded-[var(--r-lg)] border border-[var(--border)] bg-[var(--surface)] p-4 lg:sticky lg:top-20 lg:self-start",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label={labels.heading}
      data-testid="search-filter-panel"
    >
      <h2 className="text-[var(--fs-h3)] font-semibold text-[var(--text)]">{labels.heading}</h2>

      <fieldset className="flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium text-[var(--text)]">{labels.price}</legend>
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            placeholder={labels.minPrice}
            value={state.minPrice ?? ""}
            onChange={(event) =>
              setState((current) => ({ ...current, minPrice: event.target.value || undefined }))
            }
            aria-label={labels.minPrice}
          />
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            placeholder={labels.maxPrice}
            value={state.maxPrice ?? ""}
            onChange={(event) =>
              setState((current) => ({ ...current, maxPrice: event.target.value || undefined }))
            }
            aria-label={labels.maxPrice}
          />
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium text-[var(--text)]">{labels.category}</legend>
        <Select
          value={state.categoryPath ?? ""}
          onChange={(event) =>
            setState((current) => ({
              ...current,
              categoryPath: event.target.value || undefined,
            }))
          }
          aria-label={labels.category}
        >
          <option value="">{labels.categoryAll}</option>
          {categories.map((category) => (
            <option key={category.path} value={category.path}>
              {category.label}
            </option>
          ))}
        </Select>
      </fieldset>

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.apply}
          onClick={() => pushFilters(state)}
        >
          {labels.apply}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.clear}
          onClick={() => {
            const cleared: SearchFilterState = {};
            setState(cleared);
            pushFilters(cleared);
          }}
        >
          {labels.clear}
        </Button>
      </div>
    </aside>
  );
}
