// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

import { Select } from "./select";

describe("Select", () => {
  it("sets aria-invalid when error is true", () => {
    render(
      <Select error aria-label="field.region">
        <option value="lusaka">region.lusaka</option>
      </Select>,
    );
    expect(screen.getByRole("combobox", { name: "field.region" })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
});
