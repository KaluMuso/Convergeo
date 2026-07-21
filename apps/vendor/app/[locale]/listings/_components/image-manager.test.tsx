import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../../../packages/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: () => null,
}));

vi.mock("../../../../../../packages/ui/src/media/upload-dropzone", () => ({
  UploadDropzone: () => null,
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

import {
  DOWNSCALE_MAX_EDGE,
  MAX_LISTING_IMAGES,
  uploadToCloudinaryWithProgress,
  uploadWithRetry,
  wouldExceedImageCap,
} from "./image-manager";

describe("wouldExceedImageCap", () => {
  it("blocks the 9th image client-side", () => {
    expect(wouldExceedImageCap(8, 1)).toBe(true);
    expect(wouldExceedImageCap(7, 2)).toBe(true);
    expect(wouldExceedImageCap(7, 1)).toBe(false);
    expect(MAX_LISTING_IMAGES).toBe(8);
  });
});

describe("downscaleImageFile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("downscales large images before upload", async () => {
    const { downscaleImageFile } = await import("./image-manager");
    const source = new File([new Uint8Array([1, 2, 3])], "large.jpg", { type: "image/jpeg" });

    const drawImage = vi.fn();
    const toBlob = vi.fn((callback: BlobCallback) => {
      callback(new Blob(["downscaled"], { type: "image/jpeg" }));
    });

    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({
        width: 4000,
        height: 3000,
        close: vi.fn(),
      })),
    );

    vi.stubGlobal("document", {
      createElement: (tagName: string) => {
        if (tagName === "canvas") {
          return {
            width: 0,
            height: 0,
            getContext: () => ({ drawImage }),
            toBlob,
          };
        }
        throw new Error(`Unexpected element: ${tagName}`);
      },
    });

    const downscaled = await downscaleImageFile(source, {
      maxEdge: DOWNSCALE_MAX_EDGE,
      quality: 0.85,
    });

    expect(drawImage).toHaveBeenCalled();
    expect(toBlob).toHaveBeenCalled();
    expect(downscaled.size).toBeGreaterThan(0);
    expect(downscaled.type).toBe("image/jpeg");
  });
});

describe("uploadWithRetry", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("retries failed uploads before succeeding", async () => {
    const signed = {
      cloud_name: "test-cloud",
      api_key: "key",
      timestamp: 1,
      signature: "sig",
      folder: "listings/vendor-a",
      allowed_formats: "jpg,png,webp,avif",
      max_file_size: 10_485_760,
    };

    let attempts = 0;
    class MockXHR {
      upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
      status = 0;
      responseText = "";
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;

      open() {}

      send() {
        attempts += 1;
        if (attempts === 1) {
          this.status = 500;
          this.onload?.();
          return;
        }
        this.status = 200;
        this.responseText = JSON.stringify({ public_id: "listings/vendor-a/photo-1" });
        this.onload?.();
      }
    }

    vi.stubGlobal("XMLHttpRequest", MockXHR);

    const result = await uploadWithRetry(new Blob(["x"]), signed, () => undefined, 2);

    expect(result.public_id).toBe("listings/vendor-a/photo-1");
    expect(attempts).toBe(2);
  });
});

describe("uploadToCloudinaryWithProgress", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("includes max_file_size in the signed upload FormData", async () => {
    const signed = {
      cloud_name: "test-cloud",
      api_key: "key",
      timestamp: 1_715_000_000,
      signature: "sig",
      folder: "listings/vendor-a",
      allowed_formats: "jpg,png,webp,avif",
      max_file_size: 10_485_760,
    };

    const appended = new Map<string, string>();
    class MockFormData {
      append(key: string, value: string | Blob) {
        appended.set(key, typeof value === "string" ? value : "blob");
      }
    }

    class MockXHR {
      upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
      status = 200;
      responseText = JSON.stringify({ public_id: "listings/vendor-a/photo-1" });
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;

      open() {}

      send() {
        this.onload?.();
      }
    }

    vi.stubGlobal("FormData", MockFormData);
    vi.stubGlobal("XMLHttpRequest", MockXHR);

    const result = await uploadToCloudinaryWithProgress(new Blob(["x"]), signed, () => undefined);

    expect(result.public_id).toBe("listings/vendor-a/photo-1");
    expect(appended.get("max_file_size")).toBe(String(signed.max_file_size));
    expect(appended.get("api_key")).toBe(signed.api_key);
    expect(appended.get("timestamp")).toBe(String(signed.timestamp));
    expect(appended.get("signature")).toBe(signed.signature);
    expect(appended.get("folder")).toBe(signed.folder);
    expect(appended.get("allowed_formats")).toBe(signed.allowed_formats);
  });
});
