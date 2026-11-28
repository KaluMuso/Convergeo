"use client";

import { Button } from "@vergeo/ui/src/button";

export const SELECT_OFFER_EVENT = "service-offer-select";
export const REQUEST_PANEL_ID = "service-request-panel";

/**
 * Picks an offer in the request panel (a sibling client island) without prop drilling:
 * the server-rendered offer cards stay server components, this is the only JS they add.
 */
export function SelectOfferButton({
  offerId,
  label,
  testId,
}: {
  offerId: string;
  label: string;
  testId?: string;
}) {
  return (
    <Button
      type="button"
      variant="secondary"
      className="w-full rounded-md text-sm font-semibold"
      loadingLabel={label}
      data-testid={testId ?? `select-offer-${offerId}`}
      onClick={() => {
        window.dispatchEvent(new CustomEvent(SELECT_OFFER_EVENT, { detail: offerId }));
        document
          .getElementById(REQUEST_PANEL_ID)
          ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }}
    >
      {label}
    </Button>
  );
}
