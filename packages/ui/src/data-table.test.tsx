// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable } from "./data-table";

describe("DataTable", () => {
  it("renders a table and forwards className", () => {
    render(
      <DataTable className="admin-data-table min-w-full" data-testid="queue-table">
        <thead>
          <tr>
            <th>Vendor</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Acme</td>
          </tr>
        </tbody>
      </DataTable>,
    );

    const table = screen.getByTestId("queue-table");
    expect(table.tagName).toBe("TABLE");
    expect(table).toHaveClass("admin-data-table", "min-w-full");
    expect(screen.getByRole("columnheader", { name: "Vendor" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Acme" })).toBeInTheDocument();
  });
});
