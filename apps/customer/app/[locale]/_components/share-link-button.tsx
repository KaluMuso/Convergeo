"use client";

import { emitToastKey } from "@vergeo/ui/src/toast";

type ShareLinkButtonProps = {
  label: string;
  /** Title passed to the native share sheet when available. */
  title?: string;
  className?: string;
};

/**
 * Native share sheet on phones (WhatsApp is one tap away); falls back to
 * copying the current URL with a "Link copied" toast.
 */
export function ShareLinkButton({ label, title, className }: ShareLinkButtonProps) {
  const onClick = async () => {
    const url = window.location.href;
    const nav = window.navigator as Navigator & {
      share?: (data: { title?: string; url: string }) => Promise<void>;
    };
    if (typeof nav.share === "function") {
      try {
        await nav.share({ title, url });
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
      }
    }
    try {
      await nav.clipboard.writeText(url);
      emitToastKey("linkCopied", { type: "success" });
    } catch {
      emitToastKey("copyFailed", { type: "error" });
    }
  };

  return (
    <button
      type="button"
      onClick={() => void onClick()}
      data-testid="share-link-button"
      className={
        className ??
        "inline-flex min-h-11 items-center justify-center gap-2 rounded border border-border bg-surface px-4 text-sm font-medium text-text transition-colors hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
      }
    >
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4M18 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM6 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM18 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
      </svg>
      {label}
    </button>
  );
}
