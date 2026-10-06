"use client";

import { lazy, Suspense, type ComponentProps } from "react";

type TicketCheckoutProps = ComponentProps<(typeof import("./ticket-checkout"))["TicketCheckout"]>;

// Keep the paid-ticket flow off the product checkout's initial client bundle.
// SSR remains enabled so a ticket-group request renders its checkout surface.
const TicketCheckout = lazy(() =>
  import("./ticket-checkout").then((mod) => ({ default: mod.TicketCheckout })),
);

export function LazyTicketCheckout(props: TicketCheckoutProps) {
  return (
    <Suspense
      fallback={
        <section className="space-y-6 p-4" aria-busy="true" data-testid="ticket-checkout-loading">
          <h1 className="text-2xl font-semibold">{props.labels.pageTitle}</h1>
          <p role="status">{props.labels.loading}</p>
        </section>
      }
    >
      <TicketCheckout {...props} />
    </Suspense>
  );
}
