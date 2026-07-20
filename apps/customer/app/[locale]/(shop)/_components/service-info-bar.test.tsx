// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ServiceInfoBar } from "./service-info-bar";

afterEach(cleanup);

describe("ServiceInfoBar", () => {
  it("renders factual fulfillment messaging", () => {
    render(
      <ServiceInfoBar
        labels={{
          ariaLabel: "Delivery and pickup information",
          message: "Lusaka delivery · Nationwide pickup · Escrow when you pay online",
        }}
      />,
    );
    expect(screen.getByTestId("service-info-bar")).toHaveTextContent(/Lusaka delivery/i);
    expect(screen.getByTestId("service-info-bar")).not.toHaveTextContent(/MoMo checkout is live/i);
  });
});
