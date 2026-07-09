"use client";

import { createApiClient } from "@vergeo/config";
import { Input } from "@vergeo/ui/src/input";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { addRecentSearch } from "./recent-searches";

export type SearchKind = "products" | "services" | "events" | "supplies" | "vendors";

export type SuggestItem = {
  title: string;
  entity_kind: string;
  entity_id: string;
};

export type SuggestResponse = {
  query: string;
  suggestions: SuggestItem[];
};

export type SearchInputLabels = {
  placeholder: string;
  submit: string;
  ariaLabel: string;
  suggestionsLabel: string;
  noSuggestions: string;
};

export type SearchInputProps = {
  locale: string;
  labels: SearchInputLabels;
  initialQuery?: string;
  compact?: boolean;
  autoFocus?: boolean;
};

const DEBOUNCE_MS = 200;

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function buildSearchHref(locale: string, query: string): string {
  return `/${locale}/search?q=${encodeURIComponent(query.trim())}`;
}

export function SearchInput({
  locale,
  labels,
  initialQuery = "",
  compact = false,
  autoFocus = false,
}: SearchInputProps) {
  const router = useRouter();
  const listboxId = useId();
  const [value, setValue] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<SuggestItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    setValue(initialQuery);
  }, [initialQuery]);

  const navigateToSearch = useCallback(
    (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) {
        return;
      }
      addRecentSearch(trimmed);
      setIsOpen(false);
      router.push(buildSearchHref(locale, trimmed));
    },
    [locale, router],
  );

  const fetchSuggestions = useCallback(async (query: string) => {
    const trimmed = query.trim();
    if (!trimmed) {
      setSuggestions([]);
      setIsOpen(false);
      setActiveIndex(-1);
      return;
    }

    const requestId = ++requestIdRef.current;
    setIsLoading(true);

    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl() });
      const params = new URLSearchParams({ q: trimmed, limit: "8" });
      const response = await client.request<SuggestResponse>(
        `/search/suggest?${params.toString()}`,
      );
      if (requestId !== requestIdRef.current) {
        return;
      }
      setSuggestions(response.suggestions);
      setIsOpen(response.suggestions.length > 0);
      setActiveIndex(response.suggestions.length > 0 ? 0 : -1);
    } catch {
      if (requestId !== requestIdRef.current) {
        return;
      }
      setSuggestions([]);
      setIsOpen(false);
      setActiveIndex(-1);
    } finally {
      if (requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  const scheduleSuggest = useCallback(
    (query: string) => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => {
        void fetchSuggestions(query);
      }, DEBOUNCE_MS);
    },
    [fetchSuggestions],
  );

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  const handleChange = (nextValue: string) => {
    setValue(nextValue);
    scheduleSuggest(nextValue);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (activeIndex >= 0 && suggestions[activeIndex]) {
      navigateToSearch(suggestions[activeIndex].title);
      return;
    }
    navigateToSearch(value);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || suggestions.length === 0) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
      return;
    }

    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActiveIndex((current) => (current + 1) % suggestions.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        setActiveIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
        break;
      case "Enter":
        if (activeIndex >= 0 && suggestions[activeIndex]) {
          event.preventDefault();
          navigateToSearch(suggestions[activeIndex].title);
        }
        break;
      case "Escape":
        event.preventDefault();
        setIsOpen(false);
        setActiveIndex(-1);
        break;
      default:
        break;
    }
  };

  const activeSuggestionId = activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined;

  return (
    <form
      onSubmit={handleSubmit}
      className={compact ? "w-full" : "mx-auto w-full max-w-xl"}
      role="search"
    >
      <div className="relative">
        <Input
          type="search"
          name="q"
          value={value}
          onChange={(event) => handleChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (suggestions.length > 0) {
              setIsOpen(true);
            }
          }}
          onBlur={() => {
            window.setTimeout(() => setIsOpen(false), 120);
          }}
          placeholder={labels.placeholder}
          aria-label={labels.ariaLabel}
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          aria-activedescendant={isOpen ? activeSuggestionId : undefined}
          autoComplete="off"
          autoFocus={autoFocus}
          size={compact ? "sm" : "md"}
          className="pr-12"
        />
        <button
          type="submit"
          className="absolute right-1 top-1/2 inline-flex min-h-9 min-w-9 -translate-y-1/2 items-center justify-center rounded px-2 text-sm font-medium text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
          aria-label={labels.submit}
        >
          <svg
            aria-hidden
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3-3" />
          </svg>
        </button>

        {isOpen ? (
          <ul
            id={listboxId}
            role="listbox"
            aria-label={labels.suggestionsLabel}
            className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-border bg-surface shadow-1"
          >
            {suggestions.length === 0 && !isLoading ? (
              <li className="px-3 py-2 text-sm text-text-3">{labels.noSuggestions}</li>
            ) : null}
            {suggestions.map((item, index) => {
              const optionId = `${listboxId}-option-${index}`;
              const selected = index === activeIndex;
              return (
                <li
                  key={`${item.entity_kind}-${item.entity_id}`}
                  id={optionId}
                  role="option"
                  aria-selected={selected}
                  className={
                    selected
                      ? "cursor-pointer bg-bg-2 px-3 py-2 text-sm text-text"
                      : "cursor-pointer px-3 py-2 text-sm text-text hover:bg-bg"
                  }
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => navigateToSearch(item.title)}
                >
                  <span className="block truncate">{item.title}</span>
                  <span className="text-xs text-text-3">{item.entity_kind}</span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </form>
  );
}
