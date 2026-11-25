/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview */
"use client";

import { ACCENT_CHOICES } from "@vergeo/ui/src/accent-palette";
import { CategoryIcon } from "@vergeo/ui/src/category-icon-map";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { ICON_HUES } from "@vergeo/ui/src/icon-hues";
import { IconTile } from "@vergeo/ui/src/icon-tile";
import { LcShoppingCart, LcStore, LcTruck } from "@vergeo/ui/src/lucide-icons";
import { PageHeader } from "@vergeo/ui/src/page-header";
import { SectionCard } from "@vergeo/ui/src/section-card";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import { SpotIllustration } from "@vergeo/ui/src/spot-illustrations";
import { StatCard } from "@vergeo/ui/src/stat-card";
import { ThemePreference } from "@vergeo/ui/src/theme-preference";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { tokens } from "@vergeo/ui/tokens";

const SPOTS = [
  "empty-cart",
  "no-orders",
  "no-products",
  "verify-id",
  "payment-success",
  "no-results",
  "offline",
  "welcome-shop",
] as const;

export function DesignV2Section() {
  return (
    <section id="design-v2" className="flex flex-col gap-8 border-t border-border pt-8">
      <PageHeader
        title="Design system v2"
        subtitle="Neutral mono default, per-user accents, coloured icon tiles, motion and spot illustrations."
      />

      <SectionCard
        title="Accents & theme"
        description="Use Preferences below — persists to localStorage."
      >
        <ThemeProvider>
          <ThemePreference
            label="Display"
            description="Light / dark / system plus accent swatches."
            lightLabel="Light"
            darkLabel="Dark"
            systemLabel="System"
          />
        </ThemeProvider>
        <ul className="mt-4 flex flex-wrap gap-2 text-micro text-text-3">
          {ACCENT_CHOICES.map((accent) => (
            <li key={accent} className="rounded-pill border border-border px-2 py-1">
              data-accent="{accent}"
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard title="Core tokens (mono)">
        <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
          {Object.entries({
            bg: tokens.colors.bg,
            primary: tokens.colors.primary,
            accent: tokens.colors.accent,
            text: tokens.colors.text,
            success: tokens.colors.success,
          }).map(([key, value]) => (
            <div key={key} className="flex items-center gap-2 rounded border border-border p-2">
              <span
                className="size-6 shrink-0 rounded border border-border"
                style={{ background: value }}
              />
              <span>
                <dt className="font-mono text-micro text-text-3">{key}</dt>
                <dd className="font-mono text-micro">{value}</dd>
              </span>
            </div>
          ))}
        </dl>
      </SectionCard>

      <SectionCard title="Icon tiles">
        <div className="flex flex-wrap gap-3">
          {ICON_HUES.map((hue) => (
            <IconTile key={hue} hue={hue} size={48}>
              <LcStore className="size-6" duotone />
            </IconTile>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <CategoryIcon categorySlug="food" />
          <CategoryIcon categorySlug="electronics" />
          <CategoryIcon categorySlug="events" />
        </div>
      </SectionCard>

      <SectionCard title="Motion">
        <div className="motion-rise rounded-xl border border-border bg-surface p-4">
          motion-rise
        </div>
        <div className="animate-page-in mt-3 rounded-xl border border-border bg-surface p-4">
          animate-page-in
        </div>
        <div className="card-lift mt-3 cursor-default rounded-xl border border-border bg-surface p-4">
          card-lift (hover)
        </div>
        <button
          type="button"
          className="tap press-scale mt-3 rounded-lg bg-primary px-4 py-2 text-[var(--primary-btn-fg)]"
        >
          press-scale
        </button>
        <div className="motion-stagger mt-3 grid gap-2 sm:grid-cols-3">
          <Skeleton shape="line" />
          <Skeleton shape="line" />
          <Skeleton shape="line" />
        </div>
      </SectionCard>

      <SectionCard title="Stat cards">
        <div className="grid gap-3 sm:grid-cols-2">
          <StatCard
            label="Orders today"
            value="128"
            delta={{ text: "+12%", trend: "up" }}
            icon={<LcTruck className="size-5" duotone />}
            iconHue="teal"
          />
          <StatCard
            label="Revenue"
            value="K 45,200"
            delta={{ text: "−3%", trend: "down" }}
            icon={<LcShoppingCart className="size-5" duotone />}
            iconHue="blue"
          />
        </div>
      </SectionCard>

      <SectionCard title="Spot illustrations">
        <div className="motion-stagger grid grid-cols-2 gap-4 sm:grid-cols-4">
          {SPOTS.map((id) => (
            <div key={id} className="flex flex-col items-center gap-2 text-micro text-text-3">
              <SpotIllustration id={id} className="w-full text-primary" />
              {id}
            </div>
          ))}
        </div>
        <EmptyState
          illustration="no-results"
          title="No results"
          body="Try a different search."
          className="mt-4"
        />
      </SectionCard>
    </section>
  );
}
