// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

import { Textarea } from "./textarea";

describe("Textarea", () => {
  it("sets aria-invalid when error is true", () => {
    render(<Textarea error aria-label="field.notes" />);
    expect(screen.getByRole("textbox", { name: "field.notes" })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("supports uncontrolled typing", async () => {
    const user = userEvent.setup();
    render(<Textarea aria-label="field.notes" />);
    const textarea = screen.getByRole("textbox", { name: "field.notes" });
    await user.type(textarea, "note.alpha");
    expect(textarea).toHaveValue("note.alpha");
  });
});
