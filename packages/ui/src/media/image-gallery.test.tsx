// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImageGallery } from "./image-gallery";

afterEach(() => {
  cleanup();
});

const labels = {
  indicatorLabel: (current: number, total: number) => `${current} of ${total}`,
  previousLabel: "Previous image",
  nextLabel: "Next image",
};

function makeImages(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    publicId: `product/img-${index + 1}.jpg`,
    alt: `Product image ${index + 1}`,
  }));
}

describe("ImageGallery", () => {
  it("drops the 9th image and warns in development", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    render(<ImageGallery images={makeImages(9)} cloudName="test-cloud" {...labels} />);

    expect(screen.getAllByTestId(/gallery-slide-/)).toHaveLength(8);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("hard-capping at 8"));

    warnSpy.mockRestore();
  });

  it("navigates with arrow buttons and updates indicator", async () => {
    const user = userEvent.setup();

    render(<ImageGallery images={makeImages(3)} cloudName="test-cloud" {...labels} />);

    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("1 of 3");

    await user.click(screen.getByTestId("gallery-next"));
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("2 of 3");

    await user.click(screen.getByTestId("gallery-prev"));
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("1 of 3");
  });
});
