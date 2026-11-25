"use client";

import { formatK } from "@vergeo/i18n";
import { emitToastKey } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { subscribePriceDrop } from "../../../../../lib/engagement-api";

type PriceDropAlertProps = {
  listingId: string;
  locale: string;
  currentPriceNgwee: number;
};

type Preset = "any" | "pct10" | "pct20";

function targetForPreset(preset: Preset, currentPriceNgwee: number): number | undefined {
  if (preset === "any") {
    return undefined;
  }
  const factor = preset === "pct10" ? 90 : 80;
  return Math.floor((currentPriceNgwee * factor) / 100);
}

export function PriceDropAlert({ listingId, locale, currentPriceNgwee }: PriceDropAlertProps) {
  const t = useTranslations("catalog.pdp.value.priceDrop");
  const [preset, setPreset] = useState<Preset>("any");
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");

  const targetNgwee = useMemo(
    () => targetForPreset(preset, currentPriceNgwee),
    [currentPriceNgwee, preset],
  );

  const onSubscribe = async () => {
    setState("busy");
    const result = await subscribePriceDrop(listingId, targetNgwee);
    if (result === "signed_out") {
      setState("idle");
      window.location.assign(
        `/${locale}/login?next=${encodeURIComponent(window.location.pathname)}`,
      );
      return;
    }
    if (result === "error") {
      setState("idle");
      emitToastKey("actionFailed", { type: "error" });
      return;
    }
    setState("done");
  };

  return (
    <aside
      className="flex flex-col gap-2 rounded border border-border bg-bg p-3 text-sm"
      data-testid="pdp-price-drop-alert"
    >
      <p className="m-0 font-medium text-text">{t("heading")}</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("presetLegend")}>
        {(["any", "pct10", "pct20"] as const).map((key) => (
          <button
            key={key}
            type="button"
            data-testid={`price-drop-preset-${key}`}
            aria-pressed={preset === key}
            onClick={() => setPreset(key)}
            className={[
              "min-h-11 rounded border px-3 text-sm font-medium",
              preset === key
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-surface text-text",
            ].join(" ")}
          >
            {t(`presets.${key}`)}
            {key !== "any" && targetForPreset(key, currentPriceNgwee) != null
              ? ` (${formatK(targetForPreset(key, currentPriceNgwee)!)})`
              : null}
          </button>
        ))}
      </div>
      {state === "done" ? (
        <p role="status" className="m-0 text-success">
          {t("subscribed")}
        </p>
      ) : (
        <button
          type="button"
          data-testid="pdp-price-drop-subscribe"
          disabled={state === "busy"}
          onClick={() => void onSubscribe()}
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 font-semibold text-surface disabled:opacity-60"
        >
          {t("cta")}
        </button>
      )}
    </aside>
  );
}
