import { ApiError } from "@vergeo/config";

export type ListingFieldErrors = Record<string, string>;

export type ListingErrorMessages = {
  standaloneRequired: string;
  canonicalRequired?: string;
  standaloneDetailsRequired?: string;
  policyBlocked?: string;
  /** Draft could not be saved: check the highlighted fields. */
  draftInvalid?: string;
  /** Listing could not go live: category / release / verification rules. */
  publishBlocked?: string;
  /** code -> localized text for server field errors (vendor.listings.fieldErrors). */
  fieldErrors?: Record<string, string>;
  fallback: string;
};

export type ListingErrorIntent = "draft" | "publish";

export type ListingErrorResult = {
  /** Summary shown above the form. */
  message: string;
  /** Field name -> message, rendered next to the input. */
  fields: ListingFieldErrors;
  /** Field-level messages that have no input on this form (shown in the summary). */
  unplaced: string[];
};

type ServerFieldIssue = { field: string; code: string; message: string };

function readFieldIssues(error: ApiError): ServerFieldIssue[] {
  const raw = error.details?.fields;
  if (!Array.isArray(raw)) return [];
  const issues: ServerFieldIssue[] = [];
  for (const item of raw) {
    if (item && typeof item === "object") {
      const record = item as Record<string, unknown>;
      if (typeof record.field === "string") {
        issues.push({
          field: record.field,
          code: typeof record.code === "string" ? record.code : "",
          message: typeof record.message === "string" ? record.message : "",
        });
      }
    }
  }
  return issues;
}

const FORM_LEVEL_FIELDS = new Set(["_form", "vendor", "evidence_images"]);

/**
 * Turn an API failure into a summary line plus per-field messages. Draft and
 * publish failures use different wording: a draft only fails on problems with
 * the fields themselves, while publish can also be blocked by category or
 * release policy.
 */
export function describeListingError(
  error: unknown,
  messages: ListingErrorMessages,
  intent: ListingErrorIntent = "draft",
): ListingErrorResult {
  const summary = listingCreateErrorMessage(error, messages, intent);
  const fields: ListingFieldErrors = {};
  const unplaced: string[] = [];
  if (error instanceof ApiError) {
    for (const issue of readFieldIssues(error)) {
      const text = messages.fieldErrors?.[issue.code] ?? issue.message;
      if (!text) continue;
      if (FORM_LEVEL_FIELDS.has(issue.field)) {
        unplaced.push(text);
      } else if (!(issue.field in fields)) {
        fields[issue.field] = text;
      }
    }
  }
  return { message: summary, fields, unplaced };
}

export function listingCreateErrorMessage(
  error: unknown,
  messages: ListingErrorMessages,
  intent: ListingErrorIntent = "draft",
): string {
  if (error instanceof ApiError && error.code === "standalone_product_class_required") {
    return messages.standaloneRequired;
  }
  if (error instanceof ApiError) {
    if (error.code === "canonical_product_required")
      return messages.canonicalRequired ?? messages.fallback;
    if (error.code === "standalone_details_required")
      return messages.standaloneDetailsRequired ?? messages.fallback;
    if (error.code === "listing_publish_blocked")
      return messages.publishBlocked ?? messages.policyBlocked ?? messages.fallback;
    if (error.code === "listing_draft_invalid") return messages.draftInvalid ?? messages.fallback;
    if (error.code === "listing_policy_blocked") return messages.policyBlocked ?? messages.fallback;
    // Pydantic field errors (422 validation_error) and strategy-rule failures.
    if (
      (error.code === "validation_error" || error.code === "listing_strategy_invalid") &&
      readFieldIssues(error).length > 0
    ) {
      return (
        (intent === "publish" ? messages.publishBlocked : messages.draftInvalid) ??
        messages.fallback
      );
    }
  }
  return messages.fallback;
}
