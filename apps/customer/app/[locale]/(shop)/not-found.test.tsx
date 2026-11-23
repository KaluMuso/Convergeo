import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import marketing from "../../../../../packages/i18n/messages/en/marketing.json";

afterEach(cleanup);

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "en" }),
}));

import ShopNotFound from "./not-found";

describe("shop 404 not-found page", () => {
  it("renders branded heading and home recovery link", async () => {
    render(await ShopNotFound());
    expect(screen.getByRole("heading", { name: marketing.notFound.heading })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: marketing.notFound.home })).toHaveAttribute(
      "href",
      "/en",
    );
  });
});
