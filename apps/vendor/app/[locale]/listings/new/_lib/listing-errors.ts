import { ApiError } from "@vergeo/config";

export function listingCreateErrorMessage(
  error: unknown,
  messages: { standaloneRequired: string; fallback: string },
): string {
  if (error instanceof ApiError && error.code === "standalone_product_class_required") {
    return messages.standaloneRequired;
  }
  return messages.fallback;
}
