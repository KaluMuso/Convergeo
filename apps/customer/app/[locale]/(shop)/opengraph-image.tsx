import { ImageResponse } from "next/og";

/**
 * Keep this Edge route tiny: do not import `@vergeo/i18n` or `@vergeo/ui`
 * (message JSON + token graphs push the OG worker over Vercel's 1 MB limit).
 * Title/price come from searchParams set by product/event/vendor pages.
 */
export const runtime = "edge";
export const alt = "Vergeo5";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const COLORS = {
  bg: "#FAF7F2",
  bg2: "#F3EDE3",
  primary: "#2D4A7A",
  primaryTint: "#E8F0FA",
  displayInk: "#23324E",
  accent: "#C8861A",
  text2: "#6B5A3E",
} as const;

type ImageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ name?: string; price?: string }>;
};

export default async function OpenGraphImage({ searchParams }: ImageProps) {
  const { name, price } = await searchParams;
  const displayName = name?.trim() || "Vergeo5";
  const displayPrice = price?.trim() || null;

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "64px",
        background: `linear-gradient(135deg, ${COLORS.bg} 0%, ${COLORS.primaryTint} 55%, ${COLORS.bg2} 100%)`,
        color: COLORS.displayInk,
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "16px",
          fontSize: 28,
          fontWeight: 700,
          color: COLORS.primary,
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 12,
            background: COLORS.primary,
          }}
        />
        Vergeo5
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 900 }}>
        <div
          style={{
            fontSize: 72,
            lineHeight: 1.05,
            color: COLORS.displayInk,
            fontWeight: 700,
          }}
        >
          {displayName}
        </div>
        {displayPrice ? (
          <div
            style={{
              fontSize: 48,
              fontWeight: 700,
              color: COLORS.accent,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            }}
          >
            {displayPrice}
          </div>
        ) : null}
      </div>

      <div style={{ fontSize: 24, color: COLORS.text2 }}>
        Zambia&apos;s marketplace — escrow-backed shopping
      </div>
    </div>,
    {
      ...size,
    },
  );
}
