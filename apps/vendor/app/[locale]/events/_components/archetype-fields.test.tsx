import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { detailsToDraft, draftToDetails, type DetailsDraft } from "../_lib/archetype-draft";

import { ArchetypeFields } from "./archetype-fields";

import type { EventArchetype } from "@vergeo/ui/src/event-archetype";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key.replace(/^events\./, ""),
}));

afterEach(cleanup);

function Harness({ archetype, initial }: { archetype: EventArchetype; initial?: unknown }) {
  const [draft, setDraft] = useState<DetailsDraft>(() => detailsToDraft(initial));
  return (
    <>
      <ArchetypeFields archetype={archetype} draft={draft} onChange={setDraft} />
      <pre data-testid="out">{JSON.stringify(draftToDetails(archetype, draft))}</pre>
    </>
  );
}

const out = () =>
  JSON.parse(screen.getByTestId("out").textContent ?? "{}") as Record<string, unknown>;

describe("ArchetypeFields", () => {
  it("adapts sections to the archetype", () => {
    const { rerender } = render(<Harness archetype="concert" />);
    expect(screen.getByText("archetype.add.lineup")).toBeInTheDocument();
    expect(screen.getByText("archetype.fields.doors_open")).toBeInTheDocument();
    expect(screen.queryByText("archetype.add.menu_sections")).toBeNull();
    expect(screen.queryByText("archetype.fields.denomination")).toBeNull();
    // Common sections are always offered.
    expect(screen.getByText("archetype.add.sponsors")).toBeInTheDocument();
    expect(screen.getByText("archetype.add.faqs")).toBeInTheDocument();

    rerender(<Harness archetype="religious" />);
    expect(screen.getByText("archetype.fields.denomination")).toBeInTheDocument();
    expect(screen.getByText("archetype.add.agenda")).toBeInTheDocument();
    expect(screen.queryByText("archetype.add.lineup")).toBeNull();

    rerender(<Harness archetype="restaurant" />);
    expect(screen.getByText("archetype.add.menu_sections")).toBeInTheDocument();

    rerender(<Harness archetype="branded" />);
    expect(screen.getByTestId("presented-by")).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "archetype.sections.presented_by" }),
    ).toBeInTheDocument();

    rerender(<Harness archetype="generic" />);
    expect(screen.getByText("archetype.add.agenda")).toBeInTheDocument();
    expect(screen.queryByTestId("presented-by")).toBeNull();
  });

  it("adds and edits list rows and produces API json", () => {
    render(<Harness archetype="concert" />);
    fireEvent.click(screen.getByText("archetype.add.lineup"));
    const row = screen.getByTestId("row-lineup-0");
    fireEvent.change(within(row).getAllByRole("textbox")[0] as HTMLElement, {
      target: { value: "DJ Zed" },
    });
    expect(out()).toEqual({ lineup: [{ name: "DJ Zed" }] });
    fireEvent.click(within(row).getByText("archetype.remove"));
    expect(out()).toEqual({});
  });

  it("edits the restaurant menu with kwacha prices stored as ngwee", () => {
    render(<Harness archetype="restaurant" />);
    fireEvent.click(screen.getByText("archetype.add.menu_sections"));
    const editor = screen.getByTestId("menu-editor");
    const boxes = within(editor).getAllByRole("textbox");
    fireEvent.change(boxes[0] as HTMLElement, { target: { value: "Mains" } });
    fireEvent.change(boxes[1] as HTMLElement, { target: { value: "Nshima" } });
    fireEvent.change(boxes[3] as HTMLElement, { target: { value: "120.50" } });
    expect(out()).toEqual({
      menu_sections: [{ title: "Mains", items: [{ name: "Nshima", price_ngwee: 12050 }] }],
    });
  });

  it("prefills from stored details and keeps unknown-archetype keys out", () => {
    render(
      <Harness
        archetype="religious"
        initial={{ denomination: "Anglican", lineup: [{ name: "x" }] }}
      />,
    );
    expect(out()).toEqual({ denomination: "Anglican" });
  });
});
