// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const zoomLabels = {
  open: "Enlarge image",
  close: "Close image viewer",
  title: "Product images",
  zoomIn: "Zoom in",
  zoomOut: "Fit image",
};

function zoomGallery(images = makeImages(3), cloudName = "test-cloud") {
  return (
    <ImageGallery
      images={images}
      cloudName={cloudName}
      {...labels}
      zoomLabels={zoomLabels}
      imageFallbackLabel="Image unavailable"
    />
  );
}

describe("ImageGallery zoom", () => {
  it("opens the selected image, traps focus, closes with Escape and restores the trigger repeatedly", async () => {
    const user = userEvent.setup();
    render(zoomGallery());
    await user.click(screen.getByTestId("gallery-thumb-1"));
    const trigger = screen.getByRole("button", { name: "Enlarge image" });
    for (let count = 0; count < 3; count += 1) {
      await user.click(trigger);
      const dialog = await screen.findByRole("dialog", {
        name: "Product images",
      });
      expect(within(dialog).getByRole("img")).toHaveAttribute(
        "src",
        expect.stringContaining("img-2.jpg"),
      );
      const close = within(dialog).getByRole("button", {
        name: "Close image viewer",
      });
      await waitFor(() => expect(close).toHaveFocus());
      await user.tab({ shift: true });
      expect(within(dialog).getByRole("button", { name: "Next image" })).toHaveFocus();
      await user.tab();
      expect(close).toHaveFocus();
      expect(document.body.style.overflow).toBe("hidden");
      await user.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(trigger).toHaveFocus();
      expect(document.body.style.overflow).toBe("");
    }
  });

  it("navigates by keys and controls without moving the underlying gallery twice; resets zoom on navigation", async () => {
    const user = userEvent.setup();
    render(zoomGallery());
    await user.click(screen.getByRole("button", { name: "Enlarge image" }));
    const dialog = screen.getByRole("dialog");
    await user.keyboard("{ArrowLeft}{ArrowRight}");
    expect(within(dialog).getByText("2 of 3")).toBeInTheDocument();
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("1 of 3");
    await user.click(within(dialog).getByRole("button", { name: "Zoom in" }));
    expect(within(dialog).getByRole("img")).toHaveStyle({ width: "200%" });
    await user.click(within(dialog).getByRole("button", { name: "Next image" }));
    expect(within(dialog).getByRole("img")).toHaveStyle({ width: "100%" });
    expect(within(dialog).getByRole("button", { name: "Next image" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Previous image" }));
    await user.click(within(dialog).getByRole("button", { name: "Close image viewer" }));
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("2 of 3");
  });

  it("closes on scrim click and resets fit/pan state on reopening", async () => {
    const user = userEvent.setup();
    render(zoomGallery());
    const trigger = screen.getByRole("button", { name: "Enlarge image" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    const viewport = screen.getByTestId("image-zoom-viewport");
    viewport.scrollLeft = 100;
    await user.click(screen.getByRole("button", { name: "Fit image" }));
    expect(viewport.scrollLeft).toBe(0);
    await user.click(screen.getByRole("dialog"));
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    expect(screen.getByRole("button", { name: "Zoom in" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("closes and releases scroll lock on image replacement, empty gallery and unmount", async () => {
    const user = userEvent.setup();
    document.body.style.overflow = "scroll";
    const { rerender, unmount } = render(zoomGallery());
    await user.click(screen.getByRole("button", { name: "Enlarge image" }));
    rerender(zoomGallery(makeImages(3))); // Equal new arrays must not close the viewer.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    rerender(zoomGallery([{ publicId: "replacement.jpg", alt: "Replacement" }]));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("scroll");
    expect(screen.getByRole("button", { name: "Enlarge image" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Enlarge image" }));
    expect(within(screen.getByRole("dialog")).getByRole("img")).toHaveAttribute(
      "src",
      expect.stringContaining("replacement.jpg"),
    );
    rerender(zoomGallery([]));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("scroll");
    rerender(zoomGallery());
    await user.click(screen.getByRole("button", { name: "Enlarge image" }));
    unmount();
    expect(document.body.style.overflow).toBe("scroll");
    await user.keyboard("{Escape}{Tab}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    document.body.style.overflow = "";
  });

  it("handles unavailable media and permits recovery by navigating away from a failed image", async () => {
    const user = userEvent.setup();
    const { rerender } = render(zoomGallery());
    await user.click(screen.getByRole("button", { name: "Enlarge image" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.error(within(dialog).getByRole("img"));
    expect(within(dialog).getByRole("status")).toHaveTextContent("Image unavailable");
    expect(within(dialog).getByRole("button", { name: "Zoom in" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Next image" }));
    expect(within(dialog).getByRole("img")).toHaveAttribute(
      "src",
      expect.stringContaining("img-2.jpg"),
    );
    rerender(zoomGallery(makeImages(1), ""));
    await user.click(screen.getByRole("button", { name: "Enlarge image" }));
    expect(within(screen.getByRole("dialog")).getByRole("status")).toHaveTextContent(
      "Image unavailable",
    );
    rerender(zoomGallery([{ publicId: " ", alt: "Missing" }]));
    expect(screen.queryByRole("button", { name: "Enlarge image" })).not.toBeInTheDocument();
  });
});
