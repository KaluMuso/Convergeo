/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview; gated off in production */
"use client";

import { Badge } from "@vergeo/ui/src/badge";
import { CornerRibbon } from "@vergeo/ui/src/corner-ribbon";
import { EventCard } from "@vergeo/ui/src/event-card";
import { Pill } from "@vergeo/ui/src/pill";
import { PriceBlock } from "@vergeo/ui/src/price-block";
import { ProductCard } from "@vergeo/ui/src/product-card";
import { ServiceCard } from "@vergeo/ui/src/service-card";
import { StarRating } from "@vergeo/ui/src/star-rating";
import { TierPriceTable } from "@vergeo/ui/src/tier-price-table";
import { VendorCard } from "@vergeo/ui/src/vendor-card";
import { useState } from "react";

const NYANJA_LONG =
  "Zogulitsani katundu wabwino kwambiri ku msika wa Lusaka — zonse zimene mungazipeze pa Vergeo5 ndi zothandiza pa tsiku lonse.";

function PlaceholderMedia({ label, ratio = "4/3" }: { label: string; ratio?: string }) {
  return (
    <div
      aria-hidden
      className="flex w-full items-center justify-center bg-bg-2 text-sm text-text-3"
      style={{ aspectRatio: ratio }}
    >
      {label}
    </div>
  );
}

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <h3 className="font-display text-lg text-display-ink">{title}</h3>
      {children}
    </div>
  );
}

export function CardsSection() {
  const [rating, setRating] = useState(3);

  return (
    <section id="cards" className="scroll-mt-4 flex flex-col gap-6">
      <h2 className="font-display text-2xl text-display-ink">Cards & price primitives</h2>

      <SectionBlock title="Badges & ribbons">
        <div className="flex flex-wrap gap-2">
          <Badge variant="new" label="New" />
          <Badge variant="promotion" label="Sale" />
          <Badge variant="free" label="Free" />
          <Badge variant="sold_out" label="Sold out" />
        </div>
        <CornerRibbon trust="preferred" trustLabel="Preferred" tier="gold" tierLabel="Gold" />
        <Pill label="Electronics" color="#7a9ab5" />
      </SectionBlock>

      <SectionBlock title="Price block (ngwee integers)">
        <PriceBlock ngwee={125000} />
        <PriceBlock ngwee={99900} oldNgwee={149900} savingsLabel="Save K500.00" />
      </SectionBlock>

      <SectionBlock title="Star rating">
        <StarRating value={4.5} reviewCount={128} reviewCountLabel="(128 reviews)" />
        <StarRating value={0} reviewCount={0} noReviewsSlot={<span>No reviews yet</span>} />
        <StarRating
          mode="input"
          value={rating}
          onChange={setRating}
          name="preview-rating"
          inputAriaLabel="Rate this product"
        />
      </SectionBlock>

      <SectionBlock title="Tier price table">
        <TierPriceTable
          tiers={[
            { minQty: 1, ngwee: 50000 },
            { minQty: 10, ngwee: 45000 },
            { minQty: 50, ngwee: 40000 },
          ]}
          moq={5}
          quantityHeader="Qty"
          priceHeader="Unit price"
          moqLabel="MOQ:"
        />
      </SectionBlock>

      <SectionBlock title="Product card — populated & skeleton">
        <div className="grid max-w-sm gap-4">
          <ProductCard
            title={NYANJA_LONG}
            vendorLabel="Lusaka Crafts Co."
            media={<PlaceholderMedia label="Product" />}
            categoryColor="var(--cat-beauty)"
            badge={<Badge variant="featured" label="Featured" />}
            ngwee={189900}
            oldNgwee={229900}
            savingsLabel="Save K400.00"
            rating={4.2}
            reviewCount={56}
            reviewCountLabel="(56)"
            quickAddLabel="Quick add"
            wishlistLabel="Wishlist"
          />
          <ProductCard
            title="Skeleton"
            vendorLabel=""
            ngwee={0}
            rating={0}
            reviewCount={0}
            quickAddLabel=""
            wishlistLabel=""
            skeleton
          />
        </div>
      </SectionBlock>

      <SectionBlock title="Event card">
        <div className="grid max-w-sm gap-4">
          <EventCard
            title="Lusaka Night Market"
            dateLabel="Sat 12 Jul · 18:00"
            venueLabel="East Park Mall"
            media={<PlaceholderMedia label="Event" ratio="16/9" />}
            badge={<Badge variant="selling_fast" label="Selling fast" />}
            ngwee={75000}
            spotsFilled={42}
            spotsTotal={100}
            capacityLabel="spots filled"
            ctaLabel="Get tickets"
          />
          <EventCard
            title="Free community meetup"
            dateLabel="Sun 13 Jul"
            venueLabel="Arcades"
            isFree
            freeLabel="Free"
            spotsFilled={10}
            spotsTotal={50}
            capacityLabel="registered"
            ctaLabel="RSVP"
            skeleton
          />
        </div>
      </SectionBlock>

      <SectionBlock title="Service card">
        <div className="grid max-w-sm gap-4">
          <ServiceCard
            title="Plumbing — emergency call-out"
            providerLabel="FixIt Lusaka"
            media={<PlaceholderMedia label="Service" />}
            tags={[
              { label: "Licensed", color: "#3a7a4a" },
              { label: "Lusaka", color: "#2d4a7a" },
            ]}
            fromNgwee={35000}
            fromPriceLabel="From"
            rating={4.8}
            reviewCount={24}
            reviewCountLabel="(24)"
            ctaLabel="Request quote"
          />
        </div>
      </SectionBlock>

      <SectionBlock title="Vendor card">
        <div className="grid max-w-sm gap-4">
          <VendorCard
            name="Zed Fresh Foods"
            categoryLabel="Groceries"
            locationLabel="Woodlands, Lusaka"
            cover={<PlaceholderMedia label="Cover" ratio="3/1" />}
            avatar={<PlaceholderMedia label="Avatar" ratio="1/1" />}
            trust="id_verified"
            trustLabel="ID verified"
            tier="silver"
            tierLabel="Silver"
            stats={[
              { label: "Products", value: "124" },
              { label: "Rating", value: "4.6" },
            ]}
            ctaLabel="Visit store"
          />
        </div>
      </SectionBlock>
    </section>
  );
}
