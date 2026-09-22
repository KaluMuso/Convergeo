"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { ApiError } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { Modal } from "@vergeo/ui/src/modal";
import { useMemo, useState } from "react";

import { type CartMergeResolution, useSession } from "../../../lib/customer-session";

type MergeConflict = {
  listing_id: string;
  code: string;
  details: Record<string, unknown>;
};

type CustomerAuthBarrierLabels = {
  title: string;
  body: string;
  conflictLine: (listing: string, code: string) => string;
  accountChoice: string;
  guestChoice: string;
  apply: string;
  retry: string;
  signOut: string;
  failure: string;
};

const keepBarrierOpen = () => undefined;

function mergeConflicts(error: unknown): MergeConflict[] {
  if (!(error instanceof ApiError) || error.code !== "cart.merge_conflict") return [];
  const conflicts = error.details.conflicts;
  if (!Array.isArray(conflicts)) return [];
  return conflicts.filter((value): value is MergeConflict => {
    if (!value || typeof value !== "object") return false;
    const conflict = value as Partial<MergeConflict>;
    return (
      typeof conflict.listing_id === "string" &&
      typeof conflict.code === "string" &&
      typeof conflict.details === "object" &&
      conflict.details !== null
    );
  });
}

function resolutionFor(
  conflicts: MergeConflict[],
  pickupChoice: "account" | "guest",
): CartMergeResolution {
  const codesByListing = new Map<string, Set<string>>();
  for (const conflict of conflicts) {
    const codes = codesByListing.get(conflict.listing_id) ?? new Set<string>();
    codes.add(conflict.code);
    codesByListing.set(conflict.listing_id, codes);
  }

  const removeListingIds = new Set<string>();
  for (const [listingId, codes] of codesByListing) {
    if ([...codes].some((code) => !["cart.price_changed", "cart.pickup_conflict"].includes(code))) {
      removeListingIds.add(listingId);
    }
  }

  const pickupLocationChoices: Record<string, string | null> = {};
  const acceptPriceChanges = new Set<string>();
  for (const conflict of conflicts) {
    if (removeListingIds.has(conflict.listing_id)) continue;
    if (conflict.code === "cart.price_changed") {
      acceptPriceChanges.add(conflict.listing_id);
    }
    if (conflict.code === "cart.pickup_conflict") {
      const key =
        pickupChoice === "account" ? "user_pickup_location_id" : "guest_pickup_location_id";
      const selected = conflict.details[key];
      pickupLocationChoices[conflict.listing_id] = typeof selected === "string" ? selected : null;
    }
  }

  return {
    accept_price_changes: [...acceptPriceChanges].sort(),
    pickup_location_choices: pickupLocationChoices,
    remove_listing_ids: [...removeListingIds].sort(),
  };
}

export function CustomerAuthBarrier({ labels }: { labels: CustomerAuthBarrierLabels }) {
  const { error, retry } = useSession();
  const [busy, setBusy] = useState(false);
  const [retryFailed, setRetryFailed] = useState(false);
  const conflicts = useMemo(() => mergeConflicts(error), [error]);
  const hasPickupConflict = conflicts.some((conflict) => conflict.code === "cart.pickup_conflict");

  if (!error) return null;

  const runRetry = async (resolution?: CartMergeResolution) => {
    setBusy(true);
    setRetryFailed(false);
    try {
      await retry(resolution);
    } catch {
      setRetryFailed(true);
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    setBusy(true);
    try {
      const client = await getBrowserClient();
      await client.auth.signOut();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={keepBarrierOpen}
      closeOnEscape={false}
      closeOnScrimClick={false}
      title={conflicts.length ? labels.title : labels.failure}
      titleId="cart-merge-recovery-title"
    >
      <div className="space-y-4">
        {conflicts.length ? <p className="font-body text-sm text-text-2">{labels.body}</p> : null}

        {conflicts.length ? (
          <>
            <ul className="space-y-1 font-body text-sm text-text-2">
              {conflicts.map((conflict) => (
                <li key={`${conflict.listing_id}:${conflict.code}`}>
                  {labels.conflictLine(conflict.listing_id, conflict.code)}
                </li>
              ))}
            </ul>
            <p className="font-body text-sm font-medium text-display-ink">{labels.apply}</p>
          </>
        ) : null}

        {retryFailed ? (
          <p role="alert" className="font-body text-sm text-danger">
            {labels.failure}
          </p>
        ) : null}

        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          {conflicts.length ? (
            <>
              <Button
                type="button"
                loading={busy}
                loadingLabel={labels.retry}
                onClick={() => void runRetry(resolutionFor(conflicts, "account"))}
              >
                {hasPickupConflict ? labels.accountChoice : labels.apply}
              </Button>
              {hasPickupConflict ? (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={busy}
                  loadingLabel={labels.retry}
                  onClick={() => void runRetry(resolutionFor(conflicts, "guest"))}
                >
                  {labels.guestChoice}
                </Button>
              ) : null}
            </>
          ) : (
            <Button
              type="button"
              loading={busy}
              loadingLabel={labels.retry}
              onClick={() => void runRetry()}
            >
              {labels.retry}
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            disabled={busy}
            loadingLabel={labels.signOut}
            onClick={() => void signOut()}
          >
            {labels.signOut}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
