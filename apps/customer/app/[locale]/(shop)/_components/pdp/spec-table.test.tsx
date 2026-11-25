import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { groupSpecRows, PdpSpecTable } from "./spec-table";

afterEach(cleanup);

describe("groupSpecRows", () => {
  it("hides empty groups and splits grouped keys", () => {
    const groups = groupSpecRows(
      [
        { key: "features/color", value: "Grey" },
        { key: "weight", value: "12 kg" },
      ],
      { features: "Features & specs" },
    );
    expect(groups.map((g) => g.id)).toEqual(["features", "details"]);
    expect(groups[0]?.rows[0]?.key).toBe("color");
  });
});

describe("PdpSpecTable", () => {
  it("renders grouped zebra rows", () => {
    render(
      <PdpSpecTable
        groups={[
          {
            id: "features",
            title: "Features",
            rows: [{ key: "colour", value: "Black" }],
          },
        ]}
        emptyLabel="No specs"
      />,
    );
    expect(screen.getByTestId("pdp-spec-table")).toBeInTheDocument();
    expect(screen.getByText("Black")).toBeInTheDocument();
  });
});
