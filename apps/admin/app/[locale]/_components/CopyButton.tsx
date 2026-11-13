"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

type CopyButtonProps = {
  value: string;
  /** Accessible name, e.g. "Copy phone number". */
  label: string;
  className?: string;
};

/** Copy `value` to the clipboard; announces the result politely and resets after 2s. */
export async function copyText(value: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

export function CopyButton({ value, label, className = "" }: CopyButtonProps) {
  const t = useTranslations("admin.common");
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const onClick = async () => {
    const ok = await copyText(value);
    setState(ok ? "copied" : "failed");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  };

  return (
    <>
      <button
        type="button"
        aria-label={label}
        data-copy-button=""
        onClick={() => void onClick()}
        className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border px-3 text-xs font-medium text-primary hover:bg-bg-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${className}`.trim()}
      >
        {state === "copied" ? t("copied") : state === "failed" ? t("copyFailed") : t("copy")}
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {state === "copied" ? t("copied") : state === "failed" ? t("copyFailed") : ""}
      </span>
    </>
  );
}
