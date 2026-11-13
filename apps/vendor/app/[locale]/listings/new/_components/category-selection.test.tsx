import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  CategorySelection,
  categoryPath,
  eventCategoryNodes,
  type CategoryNode,
} from "@vergeo/ui/src/category-selection";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
const nodes: CategoryNode[] = [
  { id: "parent-a", parentId: null, label: "Electronics" },
  { id: "child-a", parentId: "parent-a", label: "Phones" },
  { id: "parent-b", parentId: null, label: "Clothes" },
  { id: "child-b", parentId: "parent-b", label: "Shirts" },
  { id: "orphan", parentId: "missing", label: "Unavailable" },
];
const labels = {
  category: "Category",
  subcategory: "Subcategory",
  placeholder: "Choose",
  empty: "No categories",
  unavailable: "Category unavailable",
};
afterEach(cleanup);
function Fixture({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <CategorySelection nodes={nodes} value={value} onChange={setValue} labels={labels} />
      <output data-testid="id">{value}</output>
    </>
  );
}
describe("persisted taxonomy selection", () => {
  it("hydrates an existing child with its real parent and retains its ID", () => {
    render(<Fixture initial="child-a" />);
    expect((screen.getByLabelText("Category") as HTMLSelectElement).value).toBe("parent-a");
    expect((screen.getByLabelText("Subcategory") as HTMLSelectElement).value).toBe("child-a");
    expect(screen.getByTestId("id").textContent).toBe("child-a");
  });
  it("replaces old child when parent changes and cannot show another family's child", () => {
    render(<Fixture initial="child-a" />);
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "parent-b" } });
    expect(screen.getByTestId("id").textContent).toBe("parent-b");
    expect(screen.queryByText("Phones")).toBeNull();
    fireEvent.change(screen.getByLabelText("Subcategory"), { target: { value: "child-b" } });
    expect(screen.getByTestId("id").textContent).toBe("child-b");
  });
  it("clears child to parent and clears parent to no selection", () => {
    render(<Fixture initial="child-a" />);
    fireEvent.change(screen.getByLabelText("Subcategory"), { target: { value: "" } });
    expect(screen.getByTestId("id").textContent).toBe("parent-a");
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "" } });
    expect(screen.getByTestId("id").textContent).toBe("");
    expect(screen.queryByLabelText("Subcategory")).toBeNull();
  });
  it("shows empty and stale-ID states without silently mutating an existing ID", () => {
    const onChange = vi.fn();
    render(<CategorySelection nodes={[]} value="missing" onChange={onChange} labels={labels} />);
    expect(screen.getByRole("status").textContent).toBe("No categories");
    expect(screen.getByRole("alert").textContent).toBe("Category unavailable");
    expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
  });
  it("rejects unknown, orphaned and cyclic identities", () => {
    expect(categoryPath(nodes, "orphan")).toEqual([]);
    expect(categoryPath(nodes, "absent")).toEqual([]);
    expect(
      categoryPath(
        [
          { id: "a", parentId: "b", label: "a" },
          { id: "b", parentId: "a", label: "b" },
        ],
        "a",
      ),
    ).toEqual([]);
  });
  it("disables every level while loading or read-only", () => {
    render(
      <CategorySelection
        nodes={nodes}
        value="child-a"
        onChange={vi.fn()}
        labels={labels}
        disabled
      />,
    );
    expect(
      screen.getAllByRole("combobox").every((node) => (node as HTMLSelectElement).disabled),
    ).toBe(true);
  });
});

it("uses legacy slug translation without changing canonical identity", () => {
  const messages: Record<string, string> = { "categories.pop-up-dinners": "Dîners éphémères" };
  const t = Object.assign((key: string) => messages[key] ?? key, {
    has: (key: string) => key in messages,
  });
  expect(
    eventCategoryNodes(
      [
        {
          slug: "pop-up-dinners",
          parent_slug: "nightlife",
          label_key: "events.categories.pop_up_dinners",
        },
      ],
      t,
    ),
  ).toEqual([{ id: "pop-up-dinners", parentId: "nightlife", label: "Dîners éphémères" }]);
});
