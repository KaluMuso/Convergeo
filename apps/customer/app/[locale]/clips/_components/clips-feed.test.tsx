// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import clipsMessages from "../../../../../../packages/i18n/messages/en/clips.json";

import { ClipsFeed } from "./clips-feed";
import {
  connectionKind,
  DATA_SAVER_KEY,
  mayAutoplay,
  preferredRendition,
  preloadMode,
  readStoredDataSaver,
} from "./playback-policy";
import { formatBytes, pickRendition } from "./size";

import type { Clip } from "./types";

/**
 * M17-P04 — the playback rules ARE the pebble, so most of this file is about
 * bytes that must not move: no video request before a tap, no autoplay on
 * cellular, no autoplay on an unknown connection, and never a second `<video>`.
 */

function clip(id: string, overrides: Partial<Clip> = {}): Clip {
  return {
    id,
    caption: `caption ${id}`,
    poster_url: `https://res.cloudinary.com/demo/${id}.webp`,
    duration_s: 30,
    renditions: {
      "480p": {
        url: `https://res.cloudinary.com/demo/${id}_480.mp4`,
        width: 480,
        bytes: 1_900_000,
      },
      "720p": {
        url: `https://res.cloudinary.com/demo/${id}_720.mp4`,
        width: 720,
        bytes: 4_100_000,
      },
    },
    like_count: 3,
    comment_count: 0,
    view_count: 11,
    published_at: "2026-07-27T10:00:00Z",
    vendor: { vendor_id: "v1", display_name: "Alpha Traders", slug: "alpha" },
    listings: [],
    ...overrides,
  };
}

function setConnection(value: Record<string, unknown> | undefined): void {
  Object.defineProperty(window.navigator, "connection", {
    configurable: true,
    value,
  });
}

function setReducedMotion(reduce: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: query.includes("prefers-reduced-motion") ? reduce : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

function renderFeed(items: Clip[] = [clip("c1"), clip("c2"), clip("c3")]) {
  return render(
    <NextIntlClientProvider locale="en" messages={{ clips: clipsMessages }} onError={() => {}}>
      <ClipsFeed initialItems={items} initialCursor={null} apiBaseUrl="https://api.test" />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  setReducedMotion(false);
  setConnection(undefined);
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  // jsdom has no media pipeline; play() must resolve or every tap "fails".
  Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
    configurable: true,
    value: vi.fn().mockResolvedValue(undefined),
  });
  Object.defineProperty(window.HTMLMediaElement.prototype, "load", {
    configurable: true,
    value: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// --- The policy, tested without a DOM ---------------------------------------
describe("playback policy", () => {
  it("treats an unknown connection exactly like cellular", () => {
    expect(connectionKind(undefined)).toBe("unknown");
    expect(connectionKind({ connection: {} })).toBe("unknown");
    expect(
      mayAutoplay({
        connection: "unknown",
        dataSaverOn: false,
        prefersReducedMotion: false,
        inView: true,
      }),
    ).toBe(false);
  });

  it("never autoplays on cellular, whatever else is true", () => {
    for (const dataSaverOn of [true, false]) {
      for (const prefersReducedMotion of [true, false]) {
        expect(
          mayAutoplay({ connection: "cellular", dataSaverOn, prefersReducedMotion, inView: true }),
        ).toBe(false);
      }
    }
  });

  it("autoplays only on Wi-Fi with saver off, reduced motion off, and in view", () => {
    expect(
      mayAutoplay({
        connection: "wifi",
        dataSaverOn: false,
        prefersReducedMotion: false,
        inView: true,
      }),
    ).toBe(true);

    expect(
      mayAutoplay({
        connection: "wifi",
        dataSaverOn: true,
        prefersReducedMotion: false,
        inView: true,
      }),
    ).toBe(false);
    expect(
      mayAutoplay({
        connection: "wifi",
        dataSaverOn: false,
        prefersReducedMotion: true,
        inView: true,
      }),
    ).toBe(false);
    expect(
      mayAutoplay({
        connection: "wifi",
        dataSaverOn: false,
        prefersReducedMotion: false,
        inView: false,
      }),
    ).toBe(false);
  });

  it("classifies a slow effective type as cellular but never infers Wi-Fi from speed", () => {
    expect(connectionKind({ connection: { effectiveType: "3g" } })).toBe("cellular");
    expect(connectionKind({ connection: { effectiveType: "4g" } })).toBe("unknown");
    expect(connectionKind({ connection: { type: "wifi" } })).toBe("wifi");
  });

  it("defaults data saver ON, including when storage is unreadable", () => {
    expect(readStoredDataSaver(undefined)).toBe(true);
    expect(
      readStoredDataSaver({
        getItem: () => {
          throw new Error("blocked");
        },
      }),
    ).toBe(true);
    expect(readStoredDataSaver({ getItem: () => "off" })).toBe(false);
  });

  it("never preloads unless it is Wi-Fi with saver off", () => {
    expect(preloadMode(true, "wifi")).toBe("none");
    expect(preloadMode(false, "cellular")).toBe("none");
    expect(preloadMode(false, "unknown")).toBe("none");
    expect(preloadMode(false, "wifi")).toBe("metadata");
  });

  it("picks the 480p ceiling on saver or any non-Wi-Fi connection", () => {
    expect(preferredRendition(true, "wifi")).toBe("480p");
    expect(preferredRendition(false, "unknown")).toBe("480p");
    expect(preferredRendition(false, "cellular")).toBe("480p");
    expect(preferredRendition(false, "wifi")).toBe("720p");
  });
});

// --- Poster-first ------------------------------------------------------------
describe("poster-first rendering", () => {
  it("renders no video element at all before a tap", () => {
    renderFeed();

    expect(document.querySelectorAll("video")).toHaveLength(0);
    expect(screen.getAllByTestId("clip-poster").length).toBeGreaterThan(0);
  });

  it("shows the byte-size chip before any play", () => {
    renderFeed([clip("c1")]);

    const chip = screen.getAllByTestId("clip-size-chip")[0];
    // 1_900_000 bytes at the 480p saver ceiling.
    expect(chip).toHaveTextContent("1.8 MB");
  });

  it("keeps data saver on by default so the chip quotes the smaller rendition", () => {
    renderFeed([clip("c1")]);

    expect(screen.getByTestId("clips-data-saver-toggle")).toHaveAttribute("aria-checked", "true");
  });

  it("does not render posters for clips beyond viewport +/-1", () => {
    renderFeed([clip("c1"), clip("c2"), clip("c3"), clip("c4"), clip("c5")]);

    // Active index is 0, so c1/c2 have posters and c3..c5 are placeholders.
    expect(screen.getAllByTestId("clip-poster")).toHaveLength(2);
    expect(screen.getAllByTestId("clip-poster-placeholder")).toHaveLength(3);
  });
});

// --- One recycled <video> ----------------------------------------------------
describe("the single recycled video element", () => {
  it("holds exactly one video while playing, and none while stopped", async () => {
    const user = userEvent.setup();
    renderFeed();

    await user.click(screen.getAllByTestId("clip-play-button")[0]!);
    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(1));

    // Playing a different clip must reuse the same element, never add one.
    await user.click(screen.getAllByTestId("clip-play-button")[0]!);
    expect(document.querySelectorAll("video")).toHaveLength(1);
  });

  it("detaches the source when the visitor turns data saver back on", async () => {
    const user = userEvent.setup();
    renderFeed([clip("c1")]);

    await user.click(screen.getByTestId("clips-data-saver-toggle"));
    expect(screen.getByTestId("clips-data-saver-toggle")).toHaveAttribute("aria-checked", "false");

    await user.click(screen.getByTestId("clip-play-button"));
    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(1));

    await user.click(screen.getByTestId("clips-data-saver-toggle"));

    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(0));
  });

  it("persists the data-saver choice across sessions", async () => {
    const user = userEvent.setup();
    renderFeed([clip("c1")]);

    await user.click(screen.getByTestId("clips-data-saver-toggle"));

    expect(window.localStorage.getItem(DATA_SAVER_KEY)).toBe("off");
  });
});

// --- Autoplay ---------------------------------------------------------------
describe("autoplay", () => {
  it("does not autoplay on an unknown connection even with saver off", async () => {
    window.localStorage.setItem(DATA_SAVER_KEY, "off");
    setConnection(undefined);

    renderFeed();

    await waitFor(() =>
      expect(screen.getByTestId("clips-data-saver-toggle")).toHaveAttribute(
        "aria-checked",
        "false",
      ),
    );
    expect(document.querySelectorAll("video")).toHaveLength(0);
  });

  it("does not autoplay on cellular even with saver off", async () => {
    window.localStorage.setItem(DATA_SAVER_KEY, "off");
    setConnection({ type: "cellular" });

    renderFeed();

    await waitFor(() =>
      expect(screen.getByTestId("clips-data-saver-toggle")).toHaveAttribute(
        "aria-checked",
        "false",
      ),
    );
    expect(document.querySelectorAll("video")).toHaveLength(0);
  });

  it("autoplays exactly one muted clip on Wi-Fi with saver off", async () => {
    window.localStorage.setItem(DATA_SAVER_KEY, "off");
    setConnection({ type: "wifi" });

    renderFeed();

    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(1));
    // React sets `muted` as a property, not an attribute — assert the property.
    expect((document.querySelector("video") as HTMLVideoElement).muted).toBe(true);
  });

  it("does not autoplay when reduced motion is requested", async () => {
    window.localStorage.setItem(DATA_SAVER_KEY, "off");
    setConnection({ type: "wifi" });
    setReducedMotion(true);

    renderFeed();

    await waitFor(() =>
      expect(screen.getByTestId("clips-data-saver-toggle")).toHaveAttribute(
        "aria-checked",
        "false",
      ),
    );
    expect(document.querySelectorAll("video")).toHaveLength(0);
  });

  it("honours the browser Save-Data signal even when the stored preference is off", async () => {
    window.localStorage.setItem(DATA_SAVER_KEY, "off");
    setConnection({ type: "wifi", saveData: true });

    renderFeed();

    await waitFor(() =>
      expect(screen.getByTestId("clips-data-saver-toggle")).toHaveAttribute("aria-checked", "true"),
    );
    expect(document.querySelectorAll("video")).toHaveLength(0);
  });

  it("removes the snap classes when reduced motion is requested", async () => {
    setReducedMotion(true);
    renderFeed();

    await waitFor(() =>
      expect(screen.getByTestId("clips-scroller").className).not.toContain("snap-mandatory"),
    );
  });
});

// --- Untrusted content -------------------------------------------------------
describe("untrusted captions", () => {
  it("renders an XSS attempt as text, never as markup", () => {
    const payload = '<img src=x onerror="alert(1)">';
    renderFeed([clip("c1", { caption: payload })]);

    const caption = screen.getByTestId("clip-caption");
    expect(caption).toHaveTextContent(payload);
    expect(caption.querySelector("img")).toBeNull();
  });
});

// --- States ------------------------------------------------------------------
describe("feed states", () => {
  it("shows the empty state when there are no clips", () => {
    renderFeed([]);
    expect(screen.getByTestId("clips-empty")).toBeInTheDocument();
  });

  it("leaves an overlay mount point for M17-P05 without building an overlay", () => {
    renderFeed([clip("c1")]);

    const slot = screen.getAllByTestId("clip-overlay-slot")[0];
    expect(slot).toBeInTheDocument();
    expect(slot).toBeEmptyDOMElement();
  });
});

// --- Size formatting ---------------------------------------------------------
describe("size honesty", () => {
  it("formats megabytes coarsely and kilobytes as whole numbers", () => {
    expect(formatBytes(1_900_000)).toEqual({ unit: "MB", value: "1.8" });
    expect(formatBytes(25_600)).toEqual({ unit: "KB", value: "25" });
    expect(formatBytes(0)).toBeNull();
    expect(formatBytes(null)).toBeNull();
  });

  it("falls back to the smallest available rendition rather than the largest", () => {
    const withoutSaverCeiling = clip("c1", {
      renditions: {
        "720p": { url: "https://res.cloudinary.com/demo/big.mp4", width: 720, bytes: 4_100_000 },
        "1080p": { url: "https://res.cloudinary.com/demo/huge.mp4", width: 1080, bytes: 9_000_000 },
      },
    });

    expect(pickRendition(withoutSaverCeiling, "480p")?.bytes).toBe(4_100_000);
  });
});

// --- i18n --------------------------------------------------------------------
describe("i18n completeness", () => {
  it("seeds every section M17-P05 and M17-P08 will consume", () => {
    for (const section of [
      "feed",
      "player",
      "saver",
      "size",
      "overlay",
      "share",
      "engagement",
      "cost",
      "a11y",
    ]) {
      expect(clipsMessages).toHaveProperty(section);
    }
  });
});
