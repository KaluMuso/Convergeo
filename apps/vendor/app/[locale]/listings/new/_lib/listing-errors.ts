import { ApiError } from "@vergeo/config";

export function listingCreateErrorMessage(
  error: unknown,
  messages: {
    standaloneRequired: string;
    canonicalRequired?: string;
    standaloneDetailsRequired?: string;
    policyBlocked?: string;
    fallback: string;
  },
): string {
  if (error instanceof ApiError && error.code === "standalone_product_class_required") {
    return messages.standaloneRequired;
  }
  if (error instanceof ApiError) {
    if (error.code === "canonical_product_required")
      return messages.canonicalRequired ?? messages.fallback;
    if (error.code === "standalone_details_required")
      return messages.standaloneDetailsRequired ?? messages.fallback;
    if (error.code === "listing_policy_blocked") return messages.policyBlocked ?? messages.fallback;
  }
  return messages.fallback;
}
