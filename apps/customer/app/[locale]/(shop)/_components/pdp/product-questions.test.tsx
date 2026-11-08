// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import catalog from "../../../../../../../packages/i18n/messages/en/catalog.json";

const api = vi.hoisted(() => ({
  fetchProductQuestions: vi.fn(),
  askProductQuestion: vi.fn(),
}));
vi.mock("../../../../../lib/engagement-api", () => api);

import { ProductQuestions } from "./product-questions";

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function renderQa() {
  return render(
    <NextIntlClientProvider locale="en" messages={{ catalog }}>
      <ProductQuestions productSlug="solar-panel" locale="en" />
    </NextIntlClientProvider>,
  );
}

describe("ProductQuestions", () => {
  it("lists published questions with seller answers", async () => {
    api.fetchProductQuestions.mockResolvedValue([
      {
        id: "q1",
        body: "Is the charger included?",
        answers: [
          {
            id: "a1",
            body: "Yes",
            author_role: "vendor",
            vendor_name: "Lusaka Solar",
          },
        ],
      },
    ]);
    renderQa();
    expect(
      await screen.findByText("Is the charger included?"),
    ).toBeInTheDocument();
    expect(screen.getByText("Lusaka Solar")).toBeInTheDocument();
  });

  it("validates length, then confirms a sent question", async () => {
    api.fetchProductQuestions.mockResolvedValue([]);
    api.askProductQuestion.mockResolvedValue("ok");
    renderQa();
    await screen.findByText(/No questions yet/);
    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 5");
    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "Does it work with 12V?" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    });
    expect(api.askProductQuestion).toHaveBeenCalledWith(
      "solar-panel",
      "Does it work with 12V?",
    );
    expect(screen.getByRole("status")).toHaveTextContent("Question sent");
  });
});
