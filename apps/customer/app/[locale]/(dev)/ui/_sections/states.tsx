/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview; gated off in production */
"use client";

import { Button } from "@vergeo/ui/src/button";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { ErrorState } from "@vergeo/ui/src/error-state";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import { Spinner } from "@vergeo/ui/src/spinner";

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <h3 className="font-display text-lg text-display-ink">{title}</h3>
      {children}
    </div>
  );
}

export function StatesSection() {
  return (
    <section id="states" className="scroll-mt-4 flex flex-col gap-6">
      <h2 className="font-display text-2xl text-display-ink">Feedback states</h2>

      <SectionBlock title="Skeleton">
        <Skeleton shape="block" height="6rem" />
        <Skeleton shape="line" width="80%" />
        <Skeleton shape="circle" />
      </SectionBlock>

      <SectionBlock title="Spinner">
        <div className="flex flex-wrap items-center gap-6">
          <Spinner label="Loading small" size="sm" />
          <Spinner label="Loading medium" size="md" />
          <Spinner label="Loading large" size="lg" />
        </div>
      </SectionBlock>

      <SectionBlock title="Empty state">
        <EmptyState
          icon="📦"
          title="No orders yet"
          body="When you place an order it will appear here."
          action={
            <Button loadingLabel="Loading" size="sm">
              Browse products
            </Button>
          }
        />
      </SectionBlock>

      <SectionBlock title="Error state">
        <ErrorState
          icon="⚠️"
          title="Could not load data"
          body="Check your connection and try again."
          retryLabel="Retry"
          onRetry={() => undefined}
        />
      </SectionBlock>
    </section>
  );
}
