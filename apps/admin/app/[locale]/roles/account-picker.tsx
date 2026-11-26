"use client";

import { useTranslations } from "next-intl";
import { useEffect, useId, useState } from "react";

import { accountLabel, lookupAccounts, type AccountMatch } from "../../../lib/roles-api";

const DEBOUNCE_MS = 300;

export function AccountPicker({
  value,
  onChange,
  disabled = false,
}: {
  value: AccountMatch | null;
  onChange: (account: AccountMatch | null) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("admin.rolesUi.picker");
  const inputId = useId();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AccountMatch[] | null>(null);
  const [state, setState] = useState<"idle" | "searching" | "failed">("idle");

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setResults(null);
      setState("idle");
      return;
    }
    let active = true;
    setState("searching");
    const timer = window.setTimeout(() => {
      lookupAccounts(term).then(
        (found) => {
          if (!active) return;
          setResults(found);
          setState("idle");
        },
        () => {
          if (!active) return;
          setResults(null);
          setState("failed");
        },
      );
    }, DEBOUNCE_MS);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  if (value) {
    return (
      <div
        className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-surface p-3 text-sm"
        data-testid="account-picker-selected"
      >
        <span>
          <span className="font-medium">{accountLabel(value)}</span>
          {value.display_name && value.email ? (
            <span className="block text-muted">{value.email}</span>
          ) : null}
        </span>
        <button
          type="button"
          className="min-h-11 text-sm font-medium text-primary underline"
          disabled={disabled}
          onClick={() => {
            onChange(null);
            setQuery("");
          }}
        >
          {t("change")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="block text-sm">
        {t("label")}
      </label>
      <input
        id={inputId}
        type="search"
        autoComplete="off"
        value={query}
        disabled={disabled}
        placeholder={t("placeholder")}
        aria-controls={listId}
        onChange={(event) => setQuery(event.target.value)}
        className="min-h-11 w-full rounded-md border border-border bg-surface p-2"
      />
      <div id={listId} aria-live="polite">
        {state === "searching" ? (
          <p className="text-sm text-muted">{t("searching")}</p>
        ) : state === "failed" ? (
          <p role="alert" className="text-sm text-danger">
            {t("failed")}
          </p>
        ) : results && results.length === 0 ? (
          <p className="text-sm text-muted">{t("noMatches")}</p>
        ) : results ? (
          <ul className="divide-y divide-border rounded-md border border-border bg-surface">
            {results.map((account) => (
              <li key={account.user_id}>
                <button
                  type="button"
                  className="flex min-h-11 w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-bg-2"
                  onClick={() => onChange(account)}
                >
                  <span className="font-medium">{accountLabel(account)}</span>
                  <span className="text-xs text-muted">
                    {[
                      account.display_name ? account.email : null,
                      account.roles.length ? account.roles.join(", ") : t("noRoles"),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted">{t("hint")}</p>
        )}
      </div>
    </div>
  );
}
