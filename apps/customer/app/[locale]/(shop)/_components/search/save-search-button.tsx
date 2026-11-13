"use client";

import { emitToast } from "@vergeo/ui/src/toast";
import { useState } from "react";


type SaveSearchButtonProps = {
  locale: string;
  query: string;
  labels: { cta: string; saved: string; failed: string };
};

/** Saves the current query (POST /me/saved-searches) for new-match alerts. */
export function SaveSearchButton({
  locale,
  query,
  labels,
}: SaveSearchButtonProps) {
  const [state, setState] = useState<"idle" | "busy" | "saved">("idle");

  const onClick = async () => {
    setState("busy");
    const { saveSearch } = await import("../../../../../lib/engagement-api");
    const result = await saveSearch(query, {});
    if (result === "signed_out") {
      setState("idle");
      window.location.assign(
        `/${locale}/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`,
      );
      return;
    }
    if (result === "error") {
      setState("idle");
      emitToast(labels.failed, { type: "error" });
      return;
    }
    setState("saved");
    emitToast(labels.saved, { type: "success" });
  };

  return (
    <button
      type="button"
      onClick={() => void onClick()}
      disabled={state !== "idle"}
      aria-pressed={state === "saved"}
      data-testid="save-search"
      className="inline-flex min-h-10 items-center gap-1.5 rounded-pill border border-border bg-surface px-3.5 text-sm font-semibold text-text hover:border-primary hover:text-primary disabled:opacity-70"
    >
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        className="h-4 w-4"
        fill={state === "saved" ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinejoin="round"
      >
        <path d="M6 3.5h12v17l-6-4-6 4v-17Z" />
      </svg>
      {labels.cta}
    </button>
  );
}
