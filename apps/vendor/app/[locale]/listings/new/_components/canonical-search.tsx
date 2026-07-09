"use client";

import { useEffect, useState } from "react";

import { Input, Spinner } from "../_lib/ui";

import type { createListingClient } from "../_lib/listing-client";
import type { SuggestItem } from "../_lib/types";

type ListingClient = ReturnType<typeof createListingClient>;

type CanonicalSearchProps = {
  client: ListingClient;
  onSelect: (item: SuggestItem) => void;
  selectedId: string | null;
  labels: {
    placeholder: string;
    searching: string;
    empty: string;
    hint: string;
  };
};

export function CanonicalSearch({ client, onSelect, selectedId, labels }: CanonicalSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SuggestItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      void client
        .suggestProducts(trimmed)
        .then((items) => {
          if (!cancelled) {
            setResults(items);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setResults([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [client, query]);

  return (
    <div className="flex flex-col gap-3">
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={labels.placeholder}
        autoComplete="off"
        aria-label={labels.placeholder}
      />
      <p className="text-xs text-text-3">{labels.hint}</p>
      {loading ? <Spinner label={labels.searching} /> : null}
      {!loading && query.trim().length >= 2 && results.length === 0 ? (
        <p className="text-sm text-text-2">{labels.empty}</p>
      ) : null}
      <ul className="flex flex-col gap-2" role="listbox" aria-label={labels.placeholder}>
        {results.map((item) => {
          const selected = selectedId === item.entity_id;
          return (
            <li key={item.entity_id}>
              <button
                type="button"
                role="option"
                aria-selected={selected}
                className={`min-h-11 w-full rounded-lg border px-3 py-2 text-start text-sm transition-colors ${
                  selected
                    ? "border-primary bg-primary-tint text-text"
                    : "border-border bg-surface text-text hover:bg-bg-2"
                }`}
                onClick={() => onSelect(item)}
              >
                {item.title}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
