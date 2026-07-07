// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./confirm-dialog";

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

describe("ConfirmDialog", () => {
  it("fires cancel and confirm callbacks", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        open
        title="Delete item"
        body="This cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    );

    await user.click(screen.getByTestId("confirm-dialog-cancel"));
    expect(onClose).toHaveBeenCalled();

    onClose.mockClear();
    await user.click(screen.getByTestId("confirm-dialog-confirm"));
    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("supports async onConfirm", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onConfirm = vi.fn().mockResolvedValue(undefined);

    render(
      <ConfirmDialog
        open
        title="Save"
        body="Save changes?"
        confirmLabel="Save"
        cancelLabel="Cancel"
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    );

    await user.click(screen.getByTestId("confirm-dialog-confirm"));
    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("applies destructive styling", () => {
    render(
      <ConfirmDialog
        open
        title="Remove"
        body="Sure?"
        confirmLabel="Remove"
        cancelLabel="Cancel"
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        destructive
      />,
    );

    const confirm = screen.getByTestId("confirm-dialog-confirm");
    expect(confirm).toHaveStyle({ background: "var(--danger)" });
  });
});
