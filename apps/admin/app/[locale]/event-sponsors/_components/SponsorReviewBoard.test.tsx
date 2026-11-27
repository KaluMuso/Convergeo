// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SponsorReviewBoard } from "./SponsorReviewBoard";

import type { Root } from "react-dom/client";

const listMock = vi.fn();
const reviewMock = vi.fn();

const t = (key: string) => key;

vi.mock("next-intl", () => ({
  useTranslations: () => t,
  useLocale: () => "en",
}));

vi.mock("./api", () => ({
  listEventSponsorQueue: () => listMock(),
  reviewEventSponsor: (...args: unknown[]) => reviewMock(...args),
}));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

function mount() {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  act(() => {
    root.render(<SponsorReviewBoard />);
  });
}

describe("SponsorReviewBoard", () => {
  it("renders pending sponsors after load", async () => {
    listMock.mockResolvedValue({
      items: [
        {
          event_id: "evt-1",
          title: "Gospel Night",
          slug: "gospel-night",
          event_status: "published",
          organiser_name: "Grace Events",
          sponsors: [
            {
              index: 1,
              name: "Zam",
              logo: null,
              link_url: "https://zam.example",
              tagline: null,
              status: "pending",
            },
          ],
        },
      ],
    });
    mount();
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.textContent).toContain("Gospel Night");
    expect(container.textContent).toContain("Zam");
  });
});
