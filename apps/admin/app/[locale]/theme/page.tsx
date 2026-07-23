import { LOCALES } from "@vergeo/i18n";
import {
  resolveSeasonalPreset,
  SEASONAL_PRESET_IDS,
  THEME_PRESET_LIST,
  DEFAULT_SEASONAL_PRESET,
} from "@vergeo/ui/src/theme-presets";
import { getTranslations, setRequestLocale } from "next-intl/server";

type PageProps = {
  params: Promise<{ locale: string }>;
};

// The single operator knob both apps read (see customer [locale]/layout.tsx).
const ENV_VAR = "NEXT_PUBLIC_SEASONAL_THEME";

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/**
 * Theme presets console (design intent: docs/designs/SELECTION.md §8).
 *
 * Read-only preview of the seasonal brand re-skins, showing which one shoppers
 * currently see and how to switch. Activation is a deploy-time env switch
 * (NEXT_PUBLIC_SEASONAL_THEME); one-click activation + scheduling wait on a
 * settings store (the DB persistence is out of scope for this build). The page
 * is a plain server component — RBAC is enforced in middleware.
 */
export default async function ThemePresetsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("admin.theme");

  const activeId = resolveSeasonalPreset(process.env.NEXT_PUBLIC_SEASONAL_THEME);
  const presetIds = SEASONAL_PRESET_IDS.join(", ");

  return (
    <div className="space-y-6" data-testid="admin-theme-console">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>

      <div className="rounded-lg border border-primary bg-bg p-4" data-testid="admin-theme-active">
        <p className="text-xs uppercase tracking-wide text-muted">{t("activeLabel")}</p>
        <p className="mt-1 font-semibold text-text">{t(`presets.${activeId}.name`)}</p>
        <p className="mt-1 text-sm text-muted">{t("activeHint")}</p>
      </div>

      <ul className="grid list-none gap-4 p-0 sm:grid-cols-2">
        {THEME_PRESET_LIST.map((preset) => {
          const isActive = preset.id === activeId;
          const [primary, accent, ground] = preset.swatch;
          const swatchRoles = [
            { role: "primary", color: primary },
            { role: "accent", color: accent },
            { role: "ground", color: ground },
          ] as const;

          return (
            <li
              key={preset.id}
              data-testid={`admin-theme-card-${preset.id}`}
              data-active={isActive ? "true" : undefined}
              className={`space-y-3 rounded-lg border bg-surface p-4 ${
                isActive ? "border-primary shadow-sm" : "border-border"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="font-semibold text-text">{t(`presets.${preset.i18nKey}.name`)}</p>
                <div className="flex shrink-0 gap-1">
                  {preset.id === DEFAULT_SEASONAL_PRESET ? (
                    <span className="rounded-full bg-bg px-2 py-0.5 text-xs font-medium text-muted">
                      {t("defaultBadge")}
                    </span>
                  ) : null}
                  {isActive ? (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                      {t("activeBadge")}
                    </span>
                  ) : null}
                </div>
              </div>

              <p className="text-sm text-muted">{t(`presets.${preset.i18nKey}.blurb`)}</p>

              <ul className="grid list-none gap-1.5 p-0">
                {swatchRoles.map(({ role, color }) => (
                  <li key={role} className="flex items-center gap-2 text-xs">
                    <span
                      aria-hidden={true}
                      className="h-4 w-4 shrink-0 rounded border border-border"
                      style={{ backgroundColor: color }}
                    />
                    <span className="w-16 shrink-0 text-muted">{t(`roles.${role}`)}</span>
                    <code className="font-mono text-text">{color}</code>
                  </li>
                ))}
              </ul>

              {/* Mini live preview — the preset's own ground, primary button, and
                  accent chip, so the founder sees the actual season at a glance. */}
              <div
                className="flex items-center gap-2 rounded-md border border-border p-3"
                style={{ backgroundColor: ground }}
              >
                <span
                  className="inline-flex min-h-9 items-center rounded-md px-3 text-xs font-semibold"
                  style={{ backgroundColor: primary, color: "#ffffff" }}
                >
                  {t("sampleCta")}
                </span>
                <span
                  className="inline-flex min-h-9 items-center rounded-md px-3 text-xs font-medium"
                  style={{ backgroundColor: `${accent}1a`, color: accent }}
                >
                  {t("roles.accent")}
                </span>
              </div>
            </li>
          );
        })}
      </ul>

      <section className="space-y-2 rounded-lg border border-border bg-surface p-4">
        <h2 className="font-semibold text-text">{t("activation.title")}</h2>
        <p className="text-sm text-muted">{t("activation.intro")}</p>
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted">{t("activation.envLabel")}</p>
          <code className="inline-block rounded bg-bg px-2 py-1 font-mono text-sm text-text">
            {ENV_VAR}
          </code>
        </div>
        <ol className="ml-4 list-decimal space-y-1 text-sm text-muted">
          <li>{t("activation.step1", { env: ENV_VAR, ids: presetIds })}</li>
          <li>{t("activation.step2")}</li>
        </ol>
      </section>

      <section className="space-y-1 rounded-lg border border-border bg-bg p-4">
        <h2 className="font-semibold text-text">{t("roadmap.title")}</h2>
        <p className="text-sm text-muted">{t("roadmap.body")}</p>
      </section>
    </div>
  );
}
