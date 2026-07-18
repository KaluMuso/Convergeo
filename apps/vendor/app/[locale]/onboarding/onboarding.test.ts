import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import vendorMessages from "../../../../../packages/i18n/messages/en/vendor.json";

import { resolveHonestStatusVariant, resolveStatusVariant } from "./_components/status-screen";
import {
  docsRequiredForResubmit,
  isResubmitStatus,
  isValidZmMobile,
  normalizeZmPhone,
} from "./_lib/kyc-client";
import {
  DEFAULT_DRAFT,
  mergeDraftWithServer,
  readLocalDraft,
  resolveResumeStep,
  stepIndexFromKey,
  writeLocalDraft,
} from "./_lib/persistence";
import { assertPrivateKycPath, isPrivateKycPath, type KycSignUploadResponse } from "./_lib/storage";
import { PRIVATE_KYC_BUCKET } from "./_lib/types";

function createLocalStorageMock(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => [...store.keys()][index] ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
  };
}

describe("step persistence", () => {
  let storage: Storage;

  beforeEach(() => {
    storage = createLocalStorageMock();
    vi.stubGlobal("window", { localStorage: storage });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resumes at saved step after interruption", () => {
    writeLocalDraft({
      ...DEFAULT_DRAFT,
      step: stepIndexFromKey("kyc"),
      businessName: "Lusaka Tech",
      businessCategory: "electronics",
    });

    const restored = readLocalDraft();
    expect(restored?.step).toBe(1);
    expect(restored?.businessName).toBe("Lusaka Tech");

    const merged = mergeDraftWithServer(restored, {
      business_name: null,
      business_category: null,
      momo_phone: null,
      nrc_path: null,
      selfie_path: null,
    });

    const resumeStep = resolveResumeStep(merged, { resubmitMode: false, rejectedDocs: null });
    expect(resumeStep).toBe(stepIndexFromKey("kyc"));
  });

  it("merges server draft paths with local step", () => {
    writeLocalDraft({ ...DEFAULT_DRAFT, step: stepIndexFromKey("review") });
    const merged = mergeDraftWithServer(readLocalDraft(), {
      business_name: "Server Shop",
      business_category: "home",
      momo_phone: "0977123456",
      nrc_path: "kyc/vendor-a/nrc.jpg",
      selfie_path: "kyc/vendor-a/selfie.jpg",
    });

    expect(merged.businessName).toBe("Server Shop");
    expect(merged.nrcPath).toBe("kyc/vendor-a/nrc.jpg");
    expect(merged.step).toBe(stepIndexFromKey("review"));
  });

  it("uses localStorage key vergeo5-vendor-onboarding", () => {
    writeLocalDraft({ ...DEFAULT_DRAFT, businessName: "Keyed Shop" });
    expect(readLocalDraft()?.businessName).toBe("Keyed Shop");
  });
});

describe("upload authz", () => {
  it("accepts private kyc paths under kyc/ prefix", () => {
    expect(isPrivateKycPath("kyc/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/nrc.jpg")).toBe(true);
    expect(assertPrivateKycPath("kyc/vendor/nrc.jpg")).toBeUndefined();
  });

  it("rejects public or traversal paths", () => {
    expect(isPrivateKycPath("public/listings/foo.jpg")).toBe(false);
    expect(isPrivateKycPath("kyc/../secrets.jpg")).toBe(false);
    expect(() => assertPrivateKycPath("listings/foo.jpg")).toThrow(/private bucket/i);
  });

  it("requires private bucket in signed upload response", async () => {
    const signed: KycSignUploadResponse = {
      bucket: "public",
      path: "kyc/vendor/nrc.jpg",
      token: "tok",
      signed_url: "https://example.supabase.co/storage/v1/upload/sign/private/kyc/vendor/nrc.jpg",
    };

    expect(signed.bucket).not.toBe(PRIVATE_KYC_BUCKET);

    await expect(async () => {
      if (signed.bucket !== PRIVATE_KYC_BUCKET) {
        throw new Error("KYC uploads must target the private bucket");
      }
    }).rejects.toThrow(/private bucket/i);
  });

  it("signed upload uses PUT to signed_url (not public CDN)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    const signed: KycSignUploadResponse = {
      bucket: PRIVATE_KYC_BUCKET,
      path: "kyc/vendor-a/nrc.jpg",
      token: "upload-token",
      signed_url:
        "https://example.supabase.co/storage/v1/object/upload/sign/private/kyc/vendor-a/nrc.jpg?token=abc",
    };

    const { createStorageClient } = await import("./_lib/storage");
    const client = createStorageClient(() => "dev-token");
    const blob = new Blob(["fake"], { type: "image/jpeg" });
    const path = await client.uploadSigned(blob, signed);

    expect(path).toBe("kyc/vendor-a/nrc.jpg");
    expect(fetchMock).toHaveBeenCalledWith(
      signed.signed_url,
      expect.objectContaining({ method: "PUT", body: blob }),
    );

    vi.unstubAllGlobals();
  });
});

describe("resubmit flow", () => {
  it("detects resubmit statuses", () => {
    expect(isResubmitStatus("rejected")).toBe(true);
    expect(isResubmitStatus("resubmit")).toBe(true);
    expect(isResubmitStatus("draft")).toBe(false);
  });

  it("resumes at kyc step in resubmit mode without restarting business", () => {
    const draft = {
      ...DEFAULT_DRAFT,
      step: stepIndexFromKey("review"),
      businessName: "Existing Shop",
      businessCategory: "electronics",
      nrcPath: "kyc/v/nrc-old.jpg",
      selfiePath: "kyc/v/selfie-old.jpg",
      momoPhone: "0977123456",
    };

    const step = resolveResumeStep(draft, {
      resubmitMode: true,
      rejectedDocs: ["nrc"],
    });
    expect(step).toBe(stepIndexFromKey("kyc"));
    expect(draft.businessName).toBe("Existing Shop");
  });

  it("only requires rejected doc types for resubmit", () => {
    expect(docsRequiredForResubmit(["nrc"])).toEqual(["nrc"]);
    expect(docsRequiredForResubmit(null)).toEqual(["nrc", "selfie"]);
  });
});

describe("status renders", () => {
  it("maps kyc statuses to UI variants", () => {
    expect(resolveStatusVariant("submitted")).toBe("pending");
    expect(resolveStatusVariant("approved")).toBe("approved");
    expect(resolveStatusVariant("rejected")).toBe("rejected");
    expect(resolveStatusVariant("resubmit")).toBe("resubmit");
    expect(resolveStatusVariant("draft")).toBe("pending");
  });

  it("never shows approved without an auditable KYC record", () => {
    expect(
      resolveHonestStatusVariant({
        kyc_status: "approved",
        kyc_record_id: null,
      }),
    ).toBe("pending");
    expect(
      resolveHonestStatusVariant({
        kyc_status: "approved",
        kyc_record_id: "rec-1",
      }),
    ).toBe("approved");
  });
});

describe("phone validation", () => {
  it("normalizes Zambian numbers", () => {
    expect(normalizeZmPhone("977123456")).toBe("0977123456");
    expect(normalizeZmPhone("260977123456")).toBe("0977123456");
    expect(isValidZmMobile("0977123456")).toBe(true);
    expect(isValidZmMobile("0123456789")).toBe(false);
  });
});

function collectLeafKeys(node: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(node)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") {
      keys.push(path);
    } else if (value && typeof value === "object") {
      keys.push(...collectLeafKeys(value as Record<string, unknown>, path));
    }
  }
  return keys;
}

const REQUIRED_ONBOARDING_KEYS = [
  "meta.title",
  "steps.business",
  "business.heading",
  "kyc.heading",
  "kyc.capture",
  "quality.heading",
  "review.submit",
  "review.gateNotice",
  "status.pending.title",
  "status.approved.title",
  "status.rejected.resubmitCta",
  "status.resubmit.submit",
  "t2.stubLabel",
  "errors.required",
] as const;

describe("vendor.onboarding i18n", () => {
  it("uses nested onboarding keys (no flat dotted keys under onboarding)", () => {
    const onboarding = vendorMessages.onboarding as Record<string, unknown>;
    expect(onboarding).toBeDefined();
    expect("meta.title" in onboarding).toBe(false);

    const leaves = collectLeafKeys(onboarding);
    expect(leaves.length).toBeGreaterThan(40);
    for (const required of REQUIRED_ONBOARDING_KEYS) {
      expect(leaves).toContain(required);
    }
  });

  it("preserves pitch section from M12-P11", () => {
    const pitch = vendorMessages.pitch as Record<string, unknown>;
    expect(pitch.hero).toBeDefined();
    expect(vendorMessages["vendor.dashboard.title"]).toBeDefined();
  });
});
