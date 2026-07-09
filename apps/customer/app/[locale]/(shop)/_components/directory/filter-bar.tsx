"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useTransition } from "react";

export type DirectoryFacetOption = {
  value: string;
  label: string;
};

export type DirectoryFilterLabels = {
  heading: string;
  searchPlaceholder: string;
  category: string;
  location: string;
  badges: string;
  allCategories: string;
  allLocations: string;
  preferred: string;
  verified: string;
  apply: string;
  clear: string;
};

type FilterBarProps = {
  locale: string;
  categoryOptions: DirectoryFacetOption[];
  locationOptions: DirectoryFacetOption[];
  labels: DirectoryFilterLabels;
  initialQuery: string;
  initialCategory: string;
  initialLocation: string;
  initialBadges: string[];
};

export function FilterBar({
  locale,
  categoryOptions,
  locationOptions,
  labels,
  initialQuery,
  initialCategory,
  initialLocation,
  initialBadges,
}: FilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (!value) {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      }
      params.delete("page");
      const query = params.toString();
      startTransition(() => {
        router.push(query ? `${pathname}?${query}` : pathname);
      });
    },
    [pathname, router, searchParams],
  );

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const q = String(formData.get("q") ?? "").trim();
    const category = String(formData.get("category") ?? "");
    const location = String(formData.get("location") ?? "");
    const preferred = formData.get("badge-preferred") === "on";
    const verified = formData.get("badge-verified") === "on";
    const badges = [preferred ? "preferred" : null, verified ? "verified" : null]
      .filter(Boolean)
      .join(",");

    updateParams({
      q: q || null,
      category: category || null,
      location: location || null,
      badges: badges || null,
    });
  };

  const onClear = () => {
    startTransition(() => {
      router.push(`/${locale}/directory`);
    });
  };

  return (
    <form
      onSubmit={onSubmit}
      className="mb-4 space-y-3 rounded border border-border bg-surface p-4"
      style={{ borderRadius: "var(--r)" }}
      aria-busy={isPending}
    >
      <h2 className="font-display text-base font-semibold text-text">{labels.heading}</h2>

      <label className="block space-y-1">
        <span className="text-sm text-text-2">{labels.searchPlaceholder}</span>
        <input
          name="q"
          defaultValue={initialQuery}
          placeholder={labels.searchPlaceholder}
          className="min-h-11 w-full rounded border border-border bg-bg px-3 text-sm text-text"
        />
      </label>

      <label className="block space-y-1">
        <span className="text-sm text-text-2">{labels.category}</span>
        <select
          name="category"
          defaultValue={initialCategory}
          className="min-h-11 w-full rounded border border-border bg-bg px-3 text-sm text-text"
        >
          <option value="">{labels.allCategories}</option>
          {categoryOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="block space-y-1">
        <span className="text-sm text-text-2">{labels.location}</span>
        <select
          name="location"
          defaultValue={initialLocation}
          className="min-h-11 w-full rounded border border-border bg-bg px-3 text-sm text-text"
        >
          <option value="">{labels.allLocations}</option>
          {locationOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="space-y-2">
        <legend className="text-sm text-text-2">{labels.badges}</legend>
        <label className="flex min-h-11 items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            name="badge-preferred"
            defaultChecked={initialBadges.includes("preferred")}
            className="h-4 w-4"
          />
          {labels.preferred}
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            name="badge-verified"
            defaultChecked={initialBadges.includes("verified")}
            className="h-4 w-4"
          />
          {labels.verified}
        </label>
      </fieldset>

      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          className="inline-flex min-h-11 items-center rounded-pill bg-primary px-4 text-sm font-semibold text-surface"
        >
          {labels.apply}
        </button>
        <button
          type="button"
          onClick={onClear}
          className="inline-flex min-h-11 items-center rounded-pill border border-border px-4 text-sm font-medium text-text"
        >
          {labels.clear}
        </button>
      </div>
    </form>
  );
}
