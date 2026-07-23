"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

export type NearMeToggleLabels = {
  enable: string;
  active: string;
  locating: string;
  denied: string;
  unsupported: string;
  clear: string;
  hint: string;
};

type Status = "idle" | "locating" | "denied" | "unsupported";

// ~1.1 km precision: coarse enough to respect privacy (never street-level),
// precise enough for the ~12 km proximity decay applied server-side in run_search.
const COORD_PRECISION = 2;

function roundCoord(value: number): number {
  const factor = 10 ** COORD_PRECISION;
  return Math.round(value * factor) / factor;
}

export function NearMeToggle({ locale, labels }: { locale: string; labels: NearMeToggleLabels }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<Status>("idle");

  const active = searchParams.has("lat") && searchParams.has("lng");

  const pushParams = useCallback(
    (mutate: (params: URLSearchParams) => void) => {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("page"); // a proximity change resets pagination
      mutate(params);
      router.push(`/${locale}/search?${params.toString()}`);
    },
    [locale, router, searchParams],
  );

  const disable = useCallback(() => {
    setStatus("idle");
    pushParams((params) => {
      params.delete("lat");
      params.delete("lng");
    });
  }, [pushParams]);

  const enable = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setStatus("unsupported");
      return;
    }
    setStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setStatus("idle");
        pushParams((params) => {
          params.set("lat", String(roundCoord(position.coords.latitude)));
          params.set("lng", String(roundCoord(position.coords.longitude)));
        });
      },
      () => setStatus("denied"),
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    );
  }, [pushParams]);

  let label = labels.enable;
  if (active) {
    label = labels.active;
  } else if (status === "locating") {
    label = labels.locating;
  } else if (status === "denied") {
    label = labels.denied;
  } else if (status === "unsupported") {
    label = labels.unsupported;
  }

  const disabled = status === "locating";

  return (
    <button
      type="button"
      onClick={active ? disable : enable}
      disabled={disabled}
      aria-pressed={active}
      title={active ? labels.clear : labels.hint}
      data-testid="near-me-toggle"
      className={[
        "inline-flex min-h-[44px] items-center gap-1.5 rounded-full border px-3 py-1.5",
        "text-sm font-medium transition-colors focus-visible:outline-none focus-visible:shadow-focusRing",
        active
          ? "border-primary bg-primary-tint text-primary"
          : "border-border bg-surface text-text-2 hover:text-text",
        disabled ? "opacity-60" : "",
      ].join(" ")}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="h-4 w-4 shrink-0"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 21s-7-6.4-7-11a7 7 0 1 1 14 0c0 4.6-7 11-7 11Z" />
        <circle cx="12" cy="10" r="2.5" fill={active ? "var(--surface)" : "none"} />
      </svg>
      <span>{label}</span>
    </button>
  );
}
