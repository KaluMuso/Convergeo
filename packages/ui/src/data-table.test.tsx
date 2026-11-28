// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { DataTable, DataTableView, type DataTableLabels } from "./data-table";

type Row = { id: string; name: string; score: number };

const labels: DataTableLabels = {
  sortAscending: (column) => `${column}, sorted ascending`,
  sortDescending: (column) => `${column}, sorted descending`,
  sortable: (column) => `Sort by ${column}`,
  paginationAriaLabel: "Table pages",
  paginationPrevious: "Previous",
  paginationNext: "Next",
  paginationPage: (page) => `Page ${page}`,
};

afterEach(() => {
  cleanup();
});

const sampleRows: Row[] = [
  { id: "a", name: "Zebra", score: 30 },
  { id: "b", name: "Alpha", score: 10 },
  { id: "c", name: "Mango", score: 20 },
  { id: "d", name: "Beta", score: 40 },
  { id: "e", name: "Cedar", score: 50 },
  { id: "f", name: "Delta", score: 60 },
  { id: "g", name: "Echo", score: 70 },
  { id: "h", name: "Foxtrot", score: 80 },
  { id: "i", name: "Golf", score: 90 },
  { id: "j", name: "Hotel", score: 100 },
  { id: "k", name: "India", score: 110 },
];

describe("DataTable", () => {
  it("renders a table and forwards className", () => {
    render(
      <DataTable className="admin-data-table min-w-full" data-testid="queue-table">
        <thead>
          <tr>
            <th scope="col">Vendor</th>
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

describe("DataTableView", () => {
  const columns = [
    {
      id: "name",
      header: "Name",
      sortLabel: "Name",
      sortable: true,
      getSortValue: (row: Row) => row.name,
      cell: (row: Row) => row.name,
    },
    {
      id: "score",
      header: "Score",
      sortLabel: "Score",
      sortable: true,
      getSortValue: (row: Row) => row.score,
      cell: (row: Row) => row.score,
    },
  ] as const;

  it("shows an empty state when there are no rows", () => {
    render(
      <DataTableView
        rows={[]}
        columns={columns}
        rowKey={(row) => row.id}
        labels={labels}
        empty={{ title: "Nothing here", body: "Try again later" }}
      />,
    );

    expect(screen.getByTestId("data-table-empty")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("sorts rows when a sortable header is activated", async () => {
    const user = userEvent.setup();

    render(
      <DataTableView
        rows={sampleRows.slice(0, 3)}
        columns={columns}
        rowKey={(row) => row.id}
        labels={labels}
        empty={{ title: "Empty" }}
      />,
    );

    const nameSort = screen.getByRole("button", { name: "Sort by Name" });
    await user.click(nameSort);

    const table = screen.getByRole("table");
    const bodyRows = within(table).getAllByRole("row").slice(1);
    expect(bodyRows[0]).toHaveTextContent("Alpha");
    expect(bodyRows[2]).toHaveTextContent("Zebra");

    await user.click(screen.getByRole("button", { name: "Name, sorted ascending" }));
    expect(within(table).getAllByRole("row").slice(1)[2]).toHaveTextContent("Alpha");
  });

  it("exposes aria-sort on the active column header", async () => {
    const user = userEvent.setup();

    render(
      <DataTableView
        rows={sampleRows.slice(0, 2)}
        columns={columns}
        rowKey={(row) => row.id}
        labels={labels}
        empty={{ title: "Empty" }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Sort by Score" }));
    const scoreHeader = screen.getByRole("columnheader", { name: /Score/ });
    expect(scoreHeader).toHaveAttribute("aria-sort", "ascending");
  });

  it("paginates rows when page size is exceeded", async () => {
    const user = userEvent.setup();

    render(
      <DataTableView
        rows={sampleRows}
        columns={columns}
        rowKey={(row) => row.id}
        labels={labels}
        pageSize={5}
        empty={{ title: "Empty" }}
      />,
    );

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(5);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
  });
});
