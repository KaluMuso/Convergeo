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
    const badges = [
      preferred ? "preferred" : null,
      verified ? "verified" : null,
    ]
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
      router.push(`/${locale}/vendors`);
    });
  };

  // One compact horizontal bar (search · category · location · trust chips ·
  // apply) instead of a stacked form block; wraps on phones.
  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-wrap items-center gap-2"
      aria-busy={isPending}
      aria-label={labels.heading}
    >
      <label className="relative min-w-0 flex-1 basis-full sm:basis-64">
        <span className="sr-only">{labels.searchPlaceholder}</span>
        <svg
          aria-hidden
          viewBox="0 0 24 24"
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-3"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3-3" />
        </svg>
        <input
          name="q"
          type="search"
          defaultValue={initialQuery}
          placeholder={labels.searchPlaceholder}
          className="min-h-11 w-full rounded-pill border border-border bg-surface pl-10 pr-4 text-sm text-text placeholder:text-text-3 focus:border-primary focus:outline-none"
        />
      </label>

      <label className="shrink-0">
        <span className="sr-only">{labels.category}</span>
        <select
          name="category"
          defaultValue={initialCategory}
          className="min-h-11 shrink-0 rounded-pill border border-border bg-surface px-3.5 text-sm font-medium text-text focus:border-primary focus:outline-none"
        >
          <option value="">{labels.allCategories}</option>
          {categoryOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="shrink-0">
        <span className="sr-only">{labels.location}</span>
        <select
          name="location"
          defaultValue={initialLocation}
          className="min-h-11 shrink-0 rounded-pill border border-border bg-surface px-3.5 text-sm font-medium text-text focus:border-primary focus:outline-none"
        >
          <option value="">{labels.allLocations}</option>
          {locationOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="m-0 flex shrink-0 items-center gap-2 border-0 p-0">
        <legend className="sr-only">{labels.badges}</legend>
        <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-pill border border-border bg-surface px-3.5 text-sm font-medium text-text has-[:checked]:border-primary has-[:checked]:bg-primary-tint has-[:checked]:text-primary-deep">
          <input
            type="checkbox"
            name="badge-verified"
            defaultChecked={initialBadges.includes("verified")}
            className="h-4 w-4 accent-[var(--primary)]"
          />
          {labels.verified}
        </label>
        <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-pill border border-border bg-surface px-3.5 text-sm font-medium text-text has-[:checked]:border-primary has-[:checked]:bg-primary-tint has-[:checked]:text-primary-deep">
          <input
            type="checkbox"
            name="badge-preferred"
            defaultChecked={initialBadges.includes("preferred")}
            className="h-4 w-4 accent-[var(--primary)]"
          />
          {labels.preferred}
        </label>
      </fieldset>

      <div className="flex shrink-0 gap-2">
        <button
          type="submit"
          className="inline-flex min-h-11 items-center rounded-pill bg-primary px-5 text-sm font-semibold text-[var(--primary-btn-fg)] hover:bg-[var(--primary-btn-hover)]"
        >
          {labels.apply}
        </button>
        <button
          type="button"
          onClick={onClear}
          className="inline-flex min-h-11 items-center rounded-pill px-3 text-sm font-medium text-text-2 hover:text-text"
        >
          {labels.clear}
        </button>
      </div>
    </form>
  );
}
