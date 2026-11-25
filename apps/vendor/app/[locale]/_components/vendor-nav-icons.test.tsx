// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VendorNavIcon } from "./vendor-nav-icons";

describe("VendorNavIcon", () => {
  it("renders a coloured tile for sidebar nav keys", () => {
    const { getByTestId } = render(<VendorNavIcon itemKey="orders" />);
    expect(getByTestId("icon-tile").getAttribute("data-hue")).toBe("orange");
  });
});
