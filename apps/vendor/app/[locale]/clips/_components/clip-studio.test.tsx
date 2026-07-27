// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * M17-P06 — the studio's two promises to a vendor:
 *
 * 1. **We tell you the limits before you spend your data**, and refuse an
 *    over-limit file client-side rather than after 80 MB has left the phone.
 * 2. **We never say a clip is live when it is not.** A `pending_review` clip
 *    reading as "Live" would have a vendor sending customers to a URL that
 *    shows nothing — this is asserted on the actual rendered copy.
 *
 * Plus the resilience claim: an interrupted upload retries **without** a second
 * file pick and **without** a second draft.
 */

vi.mock("next-intl", () => ({
  useTranslations: () => {
    const translate = (key: string, values?: Record<string, unknown>) =>
      values && Object.keys(values).length > 0 ? `${key}:${JSON.stringify(values)}` : key;
    return translate;
  },
}));

const listMock = vi.fn();
const createDraftMock = vi.fn();

vi.mock("../_lib/clips-client", async () => {
  const actual =
    await vi.importActual<typeof import("../_lib/clips-client")>("../_lib/clips-client");
  return {
    ...actual,
    createClipsClient: () => ({
      list: listMock,
      stats: vi.fn(),
      createDraft: createDraftMock,
      linkListing: vi.fn(),
      unlinkListing: vi.fn(),
    }),
  };
});

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "token" }, loading: false }),
}));

const uploadMock = vi.fn();
vi.mock("../_lib/upload", async () => {
  const actual = await vi.importActual<typeof import("../_lib/upload")>("../_lib/upload");
  return {
    ...actual,
    readDuration: vi.fn(async () => 20),
    uploadToCloudinary: (...args: unknown[]) => uploadMock(...args),
  };
});

import { LIVE_STATUSES } from "../_lib/clips-client";
import { MAX_CLIP_BYTES, validateDuration, validateFile } from "../_lib/upload";

import { ClipComposer } from "./clip-composer";
import { ClipList } from "./clip-list";

function clip(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    status: "pending_review",
    caption: "solar lamp",
    category_id: null,
    poster_url: null,
    duration_s: 20,
    renditions: {},
    like_count: 0,
    comment_count: 0,
    view_count: 0,
    rejection_reason: null,
    published_at: null,
    taken_down_at: null,
    created_at: "2026-07-27T10:00:00Z",
    listings: [],
    ...overrides,
  };
}

function videoFile(name = "clip.mp4", size = 5_000_000): File {
  const file = new File([new Uint8Array([1, 2, 3])], name, { type: "video/mp4" });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

beforeEach(() => {
  listMock.mockReset();
  createDraftMock.mockReset();
  uploadMock.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// --- Client-side limits ------------------------------------------------------
describe("file validation", () => {
  it("refuses a non-video", () => {
    expect(validateFile({ type: "image/jpeg", size: 100 })).toBe("not_video");
  });

  it("refuses a file over 80 MB before any byte is uploaded", () => {
    expect(validateFile({ type: "video/mp4", size: MAX_CLIP_BYTES + 1 })).toBe("too_large");
    expect(validateFile({ type: "video/mp4", size: MAX_CLIP_BYTES })).toBeNull();
  });

  it("refuses a clip over 60 seconds", () => {
    expect(validateDuration(61)).toBe("too_long");
    expect(validateDuration(60)).toBeNull();
  });

  it("does not refuse a clip whose duration the browser cannot read", () => {
    // Some browsers cannot read metadata from a freshly captured file; the
    // server re-checks the real duration from the transcode result.
    expect(validateDuration(null)).toBeNull();
    expect(validateDuration(Number.NaN)).toBeNull();
  });
});

describe("the composer", () => {
  it("states the data cost before anything is selected", () => {
    render(<ClipComposer />);
    expect(screen.getByTestId("clips-data-cost")).toBeInTheDocument();
  });

  it("rejects an over-limit file with a clear message and no draft call", async () => {
    const user = userEvent.setup();
    render(<ClipComposer />);

    await user.upload(
      screen.getByTestId("clips-file-input"),
      videoFile("big.mp4", MAX_CLIP_BYTES + 1),
    );

    await waitFor(() =>
      expect(screen.getByTestId("clips-error-message")).toHaveTextContent("clips.errors.tooLarge"),
    );
    expect(createDraftMock).not.toHaveBeenCalled();
  });

  it("explains a camera denial and offers the file picker instead of a dead end", async () => {
    const user = userEvent.setup();
    Object.defineProperty(window.navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(new Error("NotAllowedError")) },
    });

    render(<ClipComposer />);
    await user.click(screen.getByTestId("clips-record-button"));

    await waitFor(() => expect(screen.getByTestId("clips-camera-denied")).toBeInTheDocument());
    expect(screen.getByTestId("clips-use-picker")).toBeInTheDocument();
  });

  it("explains an unavailable camera rather than failing silently", async () => {
    const user = userEvent.setup();
    Object.defineProperty(window.navigator, "mediaDevices", {
      configurable: true,
      value: undefined,
    });

    render(<ClipComposer />);
    await user.click(screen.getByTestId("clips-record-button"));

    await waitFor(() => expect(screen.getByTestId("clips-camera-denied")).toBeInTheDocument());
  });

  it("surfaces the weekly cap refusal from the server", async () => {
    const user = userEvent.setup();
    createDraftMock.mockRejectedValue(
      Object.assign(new Error("nope"), { code: "clip_cap_exceeded" }),
    );

    render(<ClipComposer />);
    await user.upload(screen.getByTestId("clips-file-input"), videoFile());
    await waitFor(() => expect(screen.getByTestId("clips-selected")).toBeInTheDocument());
    await user.click(screen.getByTestId("clips-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("clips-error-message")).toHaveTextContent("clips.errors.weeklyCap"),
    );
  });

  it("explains that clips are for verified sellers", async () => {
    const user = userEvent.setup();
    createDraftMock.mockRejectedValue(Object.assign(new Error("nope"), { code: "forbidden" }));

    render(<ClipComposer />);
    await user.upload(screen.getByTestId("clips-file-input"), videoFile());
    await waitFor(() => expect(screen.getByTestId("clips-selected")).toBeInTheDocument());
    await user.click(screen.getByTestId("clips-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("clips-error-message")).toHaveTextContent(
        "clips.errors.notVerified",
      ),
    );
  });

  it("retries an interrupted upload without re-selecting or creating a second draft", async () => {
    const user = userEvent.setup();
    createDraftMock.mockResolvedValue({
      clip_id: "c1",
      cloud_name: "demo",
      api_key: "k",
      timestamp: 1,
      signature: "s",
      folder: "clips/v1",
      eager: "e",
      eager_async: "true",
      duration: 60,
      public_id: "c1",
    });
    uploadMock
      .mockImplementationOnce(() => ({
        promise: Promise.reject(new Error("boom")),
        abort: vi.fn(),
      }))
      .mockImplementationOnce(() => ({ promise: Promise.resolve(), abort: vi.fn() }));

    render(<ClipComposer />);
    await user.upload(screen.getByTestId("clips-file-input"), videoFile());
    await waitFor(() => expect(screen.getByTestId("clips-selected")).toBeInTheDocument());
    await user.click(screen.getByTestId("clips-submit"));

    await waitFor(() => expect(screen.getByTestId("clips-retry")).toBeInTheDocument());
    await user.click(screen.getByTestId("clips-retry"));

    await waitFor(() => expect(screen.getByTestId("clips-done")).toBeInTheDocument());
    // One draft, two upload attempts: no phantom clip, no second file pick.
    expect(createDraftMock).toHaveBeenCalledTimes(1);
    expect(uploadMock).toHaveBeenCalledTimes(2);
  });
});

// --- Never imply live before approval ---------------------------------------
describe("status honesty", () => {
  it("treats published as the only live status", () => {
    expect(LIVE_STATUSES.has("published")).toBe(true);
    for (const status of ["draft", "screening", "pending_review", "rejected", "taken_down"]) {
      expect(LIVE_STATUSES.has(status)).toBe(false);
    }
  });

  it("labels a pending_review clip as awaiting review, never as live", async () => {
    listMock.mockResolvedValue({
      items: [clip({ status: "pending_review" })],
      weekly_cap: 3,
      remaining_this_week: 2,
      window_days: 7,
    });

    render(<ClipList locale="en" />);

    await waitFor(() => expect(screen.getByTestId("vendor-clip-status")).toBeInTheDocument());
    expect(screen.getByTestId("vendor-clip-status")).toHaveTextContent(
      "clips.status.pending_review",
    );
    expect(screen.getByTestId("vendor-clip-status")).not.toHaveTextContent(
      "clips.status.published",
    );
    expect(screen.getByTestId("vendor-clip-status-help")).toHaveTextContent(
      "clips.statusHelp.pending_review",
    );
  });

  it("shows the rejection reason so the vendor can act on it", async () => {
    listMock.mockResolvedValue({
      items: [clip({ status: "rejected", rejection_reason: "blurry footage" })],
      weekly_cap: 3,
      remaining_this_week: 2,
      window_days: 7,
    });

    render(<ClipList locale="en" />);

    await waitFor(() => expect(screen.getByTestId("vendor-clip-rejection")).toBeInTheDocument());
    expect(screen.getByTestId("vendor-clip-rejection")).toHaveTextContent("blurry footage");
  });

  it("reflects an exhausted quota instead of offering an upload the server would refuse", async () => {
    listMock.mockResolvedValue({
      items: [],
      weekly_cap: 3,
      remaining_this_week: 0,
      window_days: 7,
    });

    render(<ClipList locale="en" />);

    await waitFor(() => expect(screen.getByTestId("clips-quota")).toBeInTheDocument());
    expect(screen.getByTestId("clips-quota")).toHaveTextContent("clips.quota.exhausted");
    expect(screen.getByTestId("clips-new-link")).toHaveAttribute("aria-disabled", "true");
  });

  it("renders the empty state when the vendor has no clips", async () => {
    listMock.mockResolvedValue({
      items: [],
      weekly_cap: 3,
      remaining_this_week: 3,
      window_days: 7,
    });

    render(<ClipList locale="en" />);

    await waitFor(() => expect(screen.getByTestId("clips-empty")).toBeInTheDocument());
  });

  it("offers a retry when the list fails to load", async () => {
    listMock.mockRejectedValue(new Error("boom"));

    render(<ClipList locale="en" />);

    await waitFor(() => expect(screen.getByTestId("clips-error")).toBeInTheDocument());
  });
});

// --- i18n completeness -------------------------------------------------------
describe("i18n completeness", () => {
  it("has a status label and help string for every clip status", async () => {
    const messages = (await import("../../../../../../packages/i18n/messages/en/vendor.json"))
      .default as { clips: { status: Record<string, string>; statusHelp: Record<string, string> } };

    for (const status of [
      "draft",
      "screening",
      "pending_review",
      "published",
      "rejected",
      "taken_down",
    ]) {
      expect(messages.clips.status[status]).toBeTruthy();
      expect(messages.clips.statusHelp[status]).toBeTruthy();
    }
  });

  it("never calls a non-published status live", async () => {
    const messages = (await import("../../../../../../packages/i18n/messages/en/vendor.json"))
      .default as { clips: { status: Record<string, string>; statusHelp: Record<string, string> } };

    for (const status of ["draft", "screening", "pending_review", "rejected", "taken_down"]) {
      expect(messages.clips.status[status]?.toLowerCase()).not.toContain("live");
      expect(messages.clips.statusHelp[status]?.toLowerCase()).not.toContain("shoppers can see");
    }
  });
});
