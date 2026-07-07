// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Pill } from "./pill";
import { tagTint } from "@vergeo/ui/tokens";

describe("Pill", () => {
  afterEach(() => {
    cleanup();
  });

  it("applies tagTint recipe", () => {
    const color = "#7AAB8A";
    const tint = tagTint(color);
    render(<Pill label="Health" color={color} />);
    const pill = screen.getByTestId("pill");
    expect(pill).toHaveStyle({
      backgroundColor: tint.bg,
      border: `1px solid ${tint.border}`,
      color: tint.text,
    });
  });
});
