import { loadNamespace, type Locale } from "@vergeo/i18n";
import { tokens } from "@vergeo/ui/tokens";
import { ImageResponse } from "next/og";
import { createTranslator } from "next-intl";

export const runtime = "edge";
export const alt = "Vergeo5";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

type ImageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ name?: string; price?: string }>;
};

export default async function OpenGraphImage({ params, searchParams }: ImageProps) {
  const { locale } = await params;
  const { name, price } = await searchParams;
  const [commonMessages, catalogMessages] = await Promise.all([
    loadNamespace(locale as Locale, "common"),
    loadNamespace(locale as Locale, "catalog"),
  ]);
  const tCommon = createTranslator({
    locale,
    messages: { common: commonMessages },
    namespace: "common",
  }) as (key: string) => string;
  const tCatalog = createTranslator({
    locale,
    messages: { catalog: catalogMessages },
    namespace: "catalog",
  }) as (key: string) => string;

  const displayName = name?.trim() || tCommon("app.name");
  const displayPrice = price?.trim() || null;
  const tagline = tCatalog("home.meta.title");

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "64px",
        background: `linear-gradient(135deg, ${tokens.colors.bg} 0%, ${tokens.colors.primaryTint} 55%, ${tokens.colors.bg2} 100%)`,
        color: tokens.colors.displayInk,
        fontFamily: tokens.fonts.body,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "16px",
          fontSize: 28,
          fontWeight: 700,
          color: tokens.colors.primary,
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 12,
            background: tokens.colors.primary,
          }}
        />
        {tCommon("app.name")}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 900 }}>
        <div
          style={{
            fontFamily: tokens.fonts.display,
            fontSize: 72,
            lineHeight: 1.05,
            color: tokens.colors.displayInk,
          }}
        >
          {displayName}
        </div>
        {displayPrice ? (
          <div
            style={{
              fontSize: 48,
              fontWeight: 700,
              color: tokens.colors.accent,
              fontFamily: tokens.fonts.mono,
            }}
          >
            {displayPrice}
          </div>
        ) : null}
      </div>

      <div style={{ fontSize: 24, color: tokens.colors.text2 }}>{tagline}</div>
    </div>,
    {
      ...size,
    },
  );
}
