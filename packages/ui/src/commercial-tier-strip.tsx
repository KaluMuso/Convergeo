import { TIER_META, COMMERCIAL_TIER_ORDER, type VendorTier } from "./vendor-ladder";

export type CommercialTierStripItem = {
  id: VendorTier;
  label: string;
  perk: string;
};

export type CommercialTierStripProps = {
  activeTier: VendorTier;
  items: CommercialTierStripItem[];
  ariaLabel: string;
  className?: string;
};

export function CommercialTierStrip({
  activeTier,
  items,
  ariaLabel,
  className,
}: CommercialTierStripProps) {
  const itemById = new Map(items.map((item) => [item.id, item]));

  return (
    <section className={className} aria-label={ariaLabel} data-testid="commercial-tier-strip">
      <div
        className="flex overflow-x-auto border-b border-border bg-surface scrollbar-none"
        role="tablist"
      >
        {COMMERCIAL_TIER_ORDER.map((tierId) => {
          const item = itemById.get(tierId);
          if (!item) {
            return null;
          }
          const isActive = tierId === activeTier;
          const accent = TIER_META[tierId].accentVar;

          return (
            <div
              key={tierId}
              role="tab"
              aria-selected={isActive}
              data-tier={tierId}
              data-testid={`commercial-tier-tab-${tierId}`}
              className="flex min-w-[7.5rem] shrink-0 flex-col items-center gap-1 border-r border-border px-4 py-3"
              style={{
                borderBottomWidth: 3,
                borderBottomStyle: "solid",
                borderBottomColor: isActive ? accent : "transparent",
                backgroundColor: isActive ? "var(--bg-2)" : undefined,
              }}
            >
              <span className="text-sm font-bold" style={{ color: isActive ? accent : undefined }}>
                {item.label}
              </span>
              <span className="text-center text-micro text-text-3">{item.perk}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
