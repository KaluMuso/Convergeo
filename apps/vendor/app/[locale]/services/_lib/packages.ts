import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { zmwDecimalToNgwee } from "../../listings/new/_lib/money";

/** Service packages — vendor client + pure validation (docs/plan/service-packages.md). */

/** A service may carry at most this many ACTIVE packages (API: `package_limit_reached`). */
export const MAX_PACKAGES = 10;

export const PACKAGE_LIMITS = {
  nameMin: 2,
  nameMax: 40,
  descriptionMax: 300,
  deliveryMin: 1,
  deliveryMax: 90,
  revisionsMax: 10,
  includesMax: 8,
  includeItemMax: 120,
} as const;

export type ServicePackage = {
  id: string;
  /** Legacy Basic/Standard/Premium label on rows that predate the open list. */
  tier?: "basic" | "standard" | "premium" | null;
  sort_order?: number;
  name: string;
  description: string | null;
  /** Integer ngwee; null = request a quote. */
  price_ngwee: number | null;
  delivery_days: number;
  revisions: number | null;
  includes: string[];
  status: "active" | "archived";
  updated_at: string | null;
};

export type PackagePayload = {
  name: string;
  description: string | null;
  price_ngwee: number | null;
  delivery_days: number;
  revisions: number | null;
  includes: string[];
};

/** What the form edits — strings, as typed. */
export type PackageDraft = {
  name: string;
  description: string;
  priceMode: "fixed" | "quote";
  price: string;
  deliveryDays: string;
  revisionsApplicable: boolean;
  revisions: string;
  includes: string;
};

export type PackageField = "name" | "description" | "price" | "delivery" | "revisions" | "includes";

export function emptyDraft(): PackageDraft {
  return {
    name: "",
    description: "",
    priceMode: "fixed",
    price: "",
    deliveryDays: "3",
    revisionsApplicable: true,
    revisions: "1",
    includes: "",
  };
}

export function draftFromPackage(
  pkg: ServicePackage,
  toZmw: (ngwee: number) => string,
): PackageDraft {
  return {
    name: pkg.name,
    description: pkg.description ?? "",
    priceMode: pkg.price_ngwee === null ? "quote" : "fixed",
    price: pkg.price_ngwee === null ? "" : toZmw(pkg.price_ngwee),
    deliveryDays: String(pkg.delivery_days),
    revisionsApplicable: pkg.revisions !== null,
    revisions: pkg.revisions === null ? "0" : String(pkg.revisions),
    includes: pkg.includes.join("\n"),
  };
}

const WHOLE = /^\d+$/;

/**
 * Mirror of the API's checks, so the vendor sees which field is wrong before a
 * round trip. Money goes through `zmwDecimalToNgwee` (BigInt) — never a float.
 */
export function validateDraft(
  draft: PackageDraft,
):
  | { ok: true; payload: PackagePayload }
  | { ok: false; errors: Partial<Record<PackageField, string>> } {
  const errors: Partial<Record<PackageField, string>> = {};
  const L = PACKAGE_LIMITS;

  const name = draft.name.trim();
  if (name.length < L.nameMin || name.length > L.nameMax) errors.name = "errors.name";

  const description = draft.description.trim();
  if (description.length > L.descriptionMax) errors.description = "errors.description";

  let price: number | null = null;
  if (draft.priceMode === "fixed") {
    try {
      price = zmwDecimalToNgwee(draft.price);
      if (price <= 0) errors.price = "errors.price";
    } catch {
      errors.price = "errors.price";
    }
  }

  const deliveryRaw = draft.deliveryDays.trim();
  const delivery = WHOLE.test(deliveryRaw) ? Number(deliveryRaw) : NaN;
  if (!Number.isInteger(delivery) || delivery < L.deliveryMin || delivery > L.deliveryMax) {
    errors.delivery = "errors.delivery";
  }

  let revisions: number | null = null;
  if (draft.revisionsApplicable) {
    const raw = draft.revisions.trim();
    revisions = WHOLE.test(raw) ? Number(raw) : NaN;
    if (!Number.isInteger(revisions) || revisions < 0 || revisions > L.revisionsMax) {
      errors.revisions = "errors.revisions";
    }
  }

  const includes = draft.includes
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (includes.length > L.includesMax || includes.some((item) => item.length > L.includeItemMax)) {
    errors.includes = "errors.includes";
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    payload: {
      name,
      description: description || null,
      price_ngwee: price,
      delivery_days: delivery,
      revisions,
      includes,
    },
  };
}

export function createPackagesClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  const base = (serviceId: string) => `/vendor/services/${encodeURIComponent(serviceId)}/packages`;
  const one = (serviceId: string, packageId: string) =>
    `${base(serviceId)}/${encodeURIComponent(packageId)}`;
  return {
    list(serviceId: string): Promise<{
      service_id: string;
      max_packages?: number;
      items: ServicePackage[];
    }> {
      return client.request(base(serviceId));
    },
    create(serviceId: string, payload: PackagePayload): Promise<ServicePackage> {
      return client.request(base(serviceId), {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    update(serviceId: string, packageId: string, payload: PackagePayload): Promise<ServicePackage> {
      return client.request(one(serviceId, packageId), {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    remove(serviceId: string, packageId: string): Promise<void> {
      return client.request(one(serviceId, packageId), { method: "DELETE" });
    },
    /** `ids` = every ACTIVE package of the service, in the desired order. */
    reorder(serviceId: string, ids: string[]): Promise<{ items: ServicePackage[] }> {
      return client.request(`${base(serviceId)}/reorder`, {
        method: "POST",
        body: JSON.stringify({ ids }),
      });
    },
  };
}
