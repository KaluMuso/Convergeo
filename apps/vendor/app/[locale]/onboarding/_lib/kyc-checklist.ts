import { resolveHonestStatusVariant } from "../_components/status-screen";

import type { KycApplication, KycDocType } from "./types";

/**
 * Seller verification as a checklist: what is needed, why, and where each item
 * stands. Derived only from the KYC application the API returns — the UI never
 * claims "approved" without the auditable record (resolveHonestStatusVariant).
 */
export type KycChecklistItemKey = "business" | "momo" | "nrc" | "selfie" | "review";

export type KycChecklistItemState =
  "not_started" | "saved" | "submitted" | "under_review" | "approved" | "rejected";

export type KycChecklistItem = {
  key: KycChecklistItemKey;
  state: KycChecklistItemState;
};

export type KycChecklist = {
  items: KycChecklistItem[];
  /** Count of items that need nothing more from the vendor. */
  doneCount: number;
  /** First item the vendor must act on, if any. */
  nextKey: KycChecklistItemKey | null;
  overall: "draft" | "pending" | "approved" | "needs_fix";
};

type ChecklistInput = Pick<
  KycApplication,
  | "kyc_status"
  | "kyc_record_id"
  | "business_name"
  | "business_archetype"
  | "business_category"
  | "momo_phone"
  | "nrc_path"
  | "selfie_path"
  | "rejected_docs"
>;

function overallFor(input: ChecklistInput): KycChecklist["overall"] {
  if (input.kyc_status === "draft") {
    return "draft";
  }
  const variant = resolveHonestStatusVariant({
    kyc_status: input.kyc_status,
    kyc_record_id: input.kyc_record_id,
  });
  if (variant === "approved") return "approved";
  if (variant === "rejected" || variant === "resubmit") return "needs_fix";
  return "pending";
}

export function buildKycChecklist(input: ChecklistInput): KycChecklist {
  const overall = overallFor(input);
  const rejectedDocs = new Set<KycDocType>(
    overall === "needs_fix" ? (input.rejected_docs ?? []) : [],
  );

  const fieldState = (present: boolean, rejected = false): KycChecklistItemState => {
    if (rejected) return "rejected";
    if (!present) return "not_started";
    if (overall === "approved") return "approved";
    if (overall === "draft") return "saved";
    if (overall === "needs_fix") return "submitted";
    return input.kyc_status === "under_review" ? "under_review" : "submitted";
  };

  const reviewState: KycChecklistItemState =
    overall === "approved"
      ? "approved"
      : overall === "needs_fix"
        ? "rejected"
        : overall === "draft"
          ? "not_started"
          : input.kyc_status === "under_review"
            ? "under_review"
            : "submitted";

  const items: KycChecklistItem[] = [
    {
      key: "business",
      state: fieldState(
        Boolean(input.business_name?.trim()) &&
          Boolean(input.business_archetype || input.business_category),
      ),
    },
    { key: "momo", state: fieldState(Boolean(input.momo_phone?.trim())) },
    { key: "nrc", state: fieldState(Boolean(input.nrc_path), rejectedDocs.has("nrc")) },
    { key: "selfie", state: fieldState(Boolean(input.selfie_path), rejectedDocs.has("selfie")) },
    { key: "review", state: reviewState },
  ];

  const isDone = (state: KycChecklistItemState) =>
    state === "approved" || state === "submitted" || state === "under_review" || state === "saved";
  const doneCount =
    items.filter((item) => item.key !== "review" && isDone(item.state)).length +
    (reviewState === "approved" ? 1 : 0);

  const firstFix = items.find((item) => item.state === "rejected" && item.key !== "review");
  const firstMissing = items.find((item) => item.state === "not_started" && item.key !== "review");
  let nextKey: KycChecklistItemKey | null = null;
  if (firstFix) {
    nextKey = firstFix.key;
  } else if (firstMissing) {
    nextKey = firstMissing.key;
  } else if (overall === "draft" || overall === "needs_fix") {
    nextKey = "review";
  }

  return { items, doneCount, nextKey, overall };
}
