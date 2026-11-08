// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { VariantLineLabel } from "./variant-line-label";

afterEach(() => cleanup());

describe("VariantLineLabel", () => {
  it("renders the chosen options with the localized template", () => {
    render(
      <VariantLineLabel
        options={[
          { group: "Colour", value: "Red" },
          { group: "Size", value: "M" },
        ]}
        template="{group}: {value}"
        separator=" · "
        testId="line-variant"
      />,
    );
    expect(screen.getByTestId("line-variant")).toHaveTextContent("Colour: Red · Size: M");
  });

  it("renders nothing for lines without a variant", () => {
    const { container } = render(
      <VariantLineLabel options={[]} template="{group}: {value}" separator=" · " />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
