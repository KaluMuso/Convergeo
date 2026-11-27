import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OFFER_FIELDS, emptyValues } from "../_lib/archetypes";

import { AttributeFields } from "./attribute-fields";

vi.mock("next-intl", () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => false }),
}));

afterEach(cleanup);

describe("AttributeFields", () => {
  it("renders the rental offer fields and reports edits", () => {
    const onChange = vi.fn();
    const defs = OFFER_FIELDS.rental;
    render(
      <AttributeFields
        scope="offer"
        idPrefix="t"
        defs={defs}
        values={emptyValues(defs)}
        errors={{ deposit_ngwee: "money" }}
        onChange={onChange}
      />,
    );
    expect(screen.getByTestId("t-attributes")).toBeInTheDocument();
    expect(screen.getByText("errors.money")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("offer.with_operator.label"));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ with_operator: true }));
  });
});
