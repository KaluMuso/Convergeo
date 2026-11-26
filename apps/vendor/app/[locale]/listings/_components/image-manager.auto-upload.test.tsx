// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/config")>();
  return {
    ...actual,
    createApiClient: () => ({ request }),
  };
});

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock("../../../../../../packages/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: () => null,
}));

vi.mock("../../../../../../packages/ui/src/media/upload-dropzone", () => ({
  UploadDropzone: ({ onFilesChange }: { onFilesChange: (files: File[]) => void }) => (
    <button
      type="button"
      data-testid="pick-files"
      onClick={() => onFilesChange([new File(["pixels"], "photo.jpg", { type: "image/jpeg" })])}
    >
      Pick
    </button>
  ),
}));

import { ImageManager } from "./image-manager";

afterEach(() => {
  cleanup();
  request.mockReset();
  vi.unstubAllGlobals();
});

describe("ImageManager auto upload", () => {
  it("uploads immediately when files are picked", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({
        width: 100,
        height: 100,
        close: vi.fn(),
      })),
    );

    request
      .mockResolvedValueOnce({
        cloud_name: "cloud",
        api_key: "key",
        timestamp: 1,
        signature: "sig",
        folder: "f",
        allowed_formats: "jpg",
        max_file_size: 1000,
      })
      .mockResolvedValueOnce({ public_id: "listings/vendor-a/p1" })
      .mockResolvedValueOnce({
        id: "img-1",
        cloudinary_public_id: "listings/vendor-a/p1",
        position: 1,
      });

    class MockXHR {
      upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
      status = 200;
      responseText = JSON.stringify({ public_id: "listings/vendor-a/p1" });
      onload: (() => void) | null = null;
      open() {}
      send() {
        this.onload?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", MockXHR);

    render(<ImageManager listingId="listing-1" images={[]} getToken={() => "token"} />);

    const pick = await waitFor(() => document.querySelector('[data-testid="pick-files"]'));
    pick?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await waitFor(() => {
      expect(request).toHaveBeenCalledWith("/media/sign", expect.any(Object));
    });
    await waitFor(() => {
      expect(request).toHaveBeenCalledWith(
        "/vendor/listings/listing-1/images",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
