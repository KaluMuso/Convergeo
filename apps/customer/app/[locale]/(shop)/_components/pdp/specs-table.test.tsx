import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { SpecsTable, specRowsFromJson } from "./specs-table";
afterEach(cleanup);
it("preserves structured values and zero/false without inventing units", () => {
  const input = {
    dimensions: { value: 10, unit: "cm" },
    features: ["Feature as supplied", "Second feature"],
    weight: 0,
    waterproof: false,
    unknown: null,
    blank: " ",
  };
  const rows = specRowsFromJson(JSON.parse(JSON.stringify(input)));
  expect(rows.map((r) => r.key)).toEqual(["dimensions", "features", "weight", "waterproof"]);
  expect(JSON.parse(rows[0]!.value)).toEqual(input.dimensions);
  expect(JSON.parse(rows[1]!.value)).toEqual(input.features);
  expect(rows[2]!.value).toBe("0");
  expect(rows[3]!.value).toBe("false");
  expect(rows.some((r) => r.value.includes("[object Object]"))).toBe(false);
});
it("renders multiline and untrusted detail text as text, with an accessible empty state", () => {
  const { container, rerender } = render(
    <SpecsTable
      rows={specRowsFromJson({
        care: "<script>alert(1)</script>\nSecond line",
      })}
      heading="Specifications"
      emptyLabel="No details supplied"
    />,
  );
  expect(screen.getByRole("heading", { name: "Specifications" })).toBeInTheDocument();
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("dd")?.textContent).toBe("<script>alert(1)</script>\nSecond line");
  rerender(<SpecsTable rows={[]} heading="Specifications" emptyLabel="No details supplied" />);
  expect(screen.getByText("No details supplied")).toBeInTheDocument();
});
