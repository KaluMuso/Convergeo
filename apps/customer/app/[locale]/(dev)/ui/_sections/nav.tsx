/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview; gated off in production */
"use client";

import { BottomNav } from "@vergeo/ui/src/bottom-nav";
import { Breadcrumbs } from "@vergeo/ui/src/breadcrumbs";
import { LoadMorePagination, NumberedPagination } from "@vergeo/ui/src/pagination";
import { Stepper } from "@vergeo/ui/src/stepper";
import { Tabs } from "@vergeo/ui/src/tabs";
import { TopNav } from "@vergeo/ui/src/top-nav";
import { useState } from "react";

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <h3 className="font-display text-lg text-display-ink">{title}</h3>
      {children}
    </div>
  );
}

const navIcon = (glyph: string) => (
  <span aria-hidden className="text-base leading-none">
    {glyph}
  </span>
);

export function NavSection() {
  const [page, setPage] = useState(2);
  const [loadingMore, setLoadingMore] = useState(false);

  return (
    <section id="nav" className="scroll-mt-4 flex flex-col gap-6">
      <h2 className="font-display text-2xl text-display-ink">Navigation</h2>

      <SectionBlock title="Top nav">
        <div className="overflow-hidden rounded-lg border border-border">
          <TopNav
            logo={<span className="font-display text-lg text-primary">Vergeo5</span>}
            searchSlot={
              <input
                type="search"
                placeholder="Search…"
                aria-label="Search"
                className="h-10 w-full max-w-xs rounded border border-border bg-surface px-3 text-sm"
              />
            }
            cartIcon={navIcon("🛒")}
            cartCount={3}
            cartHref="#cart"
            cartLabel="Cart"
            skipLinkTargetId="ui-preview-main"
            navAriaLabel="Main"
          />
        </div>
      </SectionBlock>

      <SectionBlock title="Bottom nav">
        <div className="relative h-36 overflow-hidden rounded-lg border border-border bg-bg-2">
          <BottomNav
            ariaLabel="Primary"
            desktopHiddenClassName=""
            items={[
              { key: "home", icon: navIcon("🏠"), label: "Home", href: "#", active: true },
              {
                key: "search",
                icon: navIcon("🔍"),
                label: "Search",
                href: "#search",
                active: false,
              },
              {
                key: "cart",
                icon: navIcon("🛒"),
                label: "Cart",
                href: "#cart",
                active: false,
                badge: 2,
              },
              {
                key: "orders",
                icon: navIcon("📋"),
                label: "Orders",
                href: "#orders",
                active: false,
              },
              {
                key: "account",
                icon: navIcon("👤"),
                label: "Account",
                href: "#account",
                active: false,
              },
            ]}
          />
        </div>
      </SectionBlock>

      <SectionBlock title="Tabs">
        <Tabs
          ariaLabel="Preview tabs"
          items={[
            { key: "all", label: "All", panel: <p className="text-text-2">All items panel</p> },
            {
              key: "products",
              label: "Products",
              panel: <p className="text-text-2">Products panel</p>,
            },
            {
              key: "services",
              label: "Services",
              panel: <p className="text-text-2">Services panel</p>,
              disabled: true,
            },
          ]}
        />
      </SectionBlock>

      <SectionBlock title="Breadcrumbs">
        <Breadcrumbs
          ariaLabel="Breadcrumb"
          ellipsisLabel="…"
          items={[
            { key: "home", label: "Home", href: "#" },
            { key: "cat", label: "Electronics", href: "#" },
            { key: "sub", label: "Phones", href: "#" },
            { key: "item", label: "Samsung A15" },
          ]}
        />
      </SectionBlock>

      <SectionBlock title="Stepper">
        <Stepper
          currentStep={1}
          stepAnnouncement={(current, total) => `Step ${current} of ${total}`}
          doneIndicator="✓"
          steps={[
            { key: "cart", label: "Cart" },
            { key: "address", label: "Address" },
            { key: "pay", label: "Payment" },
            { key: "done", label: "Done" },
          ]}
        />
      </SectionBlock>

      <SectionBlock title="Pagination">
        <LoadMorePagination
          onLoadMore={() => {
            setLoadingMore(true);
            setTimeout(() => setLoadingMore(false), 800);
          }}
          loading={loadingMore}
          remainingCount={12}
          loadMoreLabel="Load more"
          loadingLabel="Loading…"
          remainingLabel={(count) => `${count} more items`}
        />
        <NumberedPagination
          page={page}
          totalPages={5}
          onPageChange={setPage}
          previousLabel="Previous"
          nextLabel="Next"
          pageLabel={(n) => `Page ${n}`}
          ariaLabel="Results pages"
        />
      </SectionBlock>
    </section>
  );
}
