import type { DispatchCutoffState } from "./dispatch-cutoff";

/**
 * "Top 3 things to do" on the vendor home. Pure ranking so the order is
 * predictable and testable: verification blockers first, then orders waiting
 * on the vendor, then a pending-review notice, then catalogue / profile upkeep.
 */
export type HomeTaskKey =
  | "kycFix"
  | "kycFinish"
  | "kycPending"
  | "ordersWaiting"
  | "ordersWaitingUrgent"
  | "ordersWaitingAfterCutoff"
  | "catalogueProducts"
  | "catalogueServices"
  | "catalogueEvents"
  | "profile";

export type HomeTaskTone = "danger" | "warning" | "info" | "neutral";

export type HomeTask = {
  key: HomeTaskKey;
  /** Path after the locale prefix. */
  href: string;
  tone: HomeTaskTone;
  count?: number;
};

export type HomeTaskInput = {
  /** null when the KYC application could not be loaded (never block on it). */
  kycOverall: "draft" | "pending" | "approved" | "needs_fix" | null;
  needsActionCount: number;
  /** Any waiting order is a delivery order (bound by the 14:00 cut-off). */
  hasDeliveryWaiting: boolean;
  cutoff: DispatchCutoffState;
  sellerKind: "products" | "services" | "events";
};

export const MAX_HOME_TASKS = 3;

export function buildHomeTasks(input: HomeTaskInput): HomeTask[] {
  const tasks: HomeTask[] = [];

  if (input.kycOverall === "needs_fix") {
    tasks.push({ key: "kycFix", href: "/onboarding/status", tone: "danger" });
  } else if (input.kycOverall === "draft") {
    tasks.push({ key: "kycFinish", href: "/onboarding", tone: "warning" });
  }

  if (input.needsActionCount > 0) {
    let key: HomeTaskKey = "ordersWaiting";
    let tone: HomeTaskTone = "warning";
    if (input.hasDeliveryWaiting && input.cutoff.phase === "before" && input.cutoff.urgent) {
      key = "ordersWaitingUrgent";
      tone = "danger";
    } else if (input.hasDeliveryWaiting && input.cutoff.phase === "after") {
      key = "ordersWaitingAfterCutoff";
    }
    tasks.push({ key, href: "/orders", tone, count: input.needsActionCount });
  }

  // Informational only (nothing for the vendor to do), so it ranks after
  // orders that are waiting on them.
  if (input.kycOverall === "pending") {
    tasks.push({ key: "kycPending", href: "/onboarding/status", tone: "info" });
  }

  const catalogue: HomeTask =
    input.sellerKind === "services"
      ? { key: "catalogueServices", href: "/services", tone: "neutral" }
      : input.sellerKind === "events"
        ? { key: "catalogueEvents", href: "/events", tone: "neutral" }
        : { key: "catalogueProducts", href: "/listings", tone: "neutral" };
  tasks.push(catalogue);
  tasks.push({ key: "profile", href: "/profile", tone: "neutral" });

  return tasks.slice(0, MAX_HOME_TASKS);
}
