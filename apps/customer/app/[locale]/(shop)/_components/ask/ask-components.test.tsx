// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@vergeo/config";
import { NextIntlClientProvider } from "next-intl";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/config", async () => {
  const actual = await vi.importActual<typeof import("@vergeo/config")>("@vergeo/config");
  return { ...actual, createApiClient: () => ({ request }) };
});

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: null, user: null, loading: false }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import { ZeroResults } from "../search/zero-results";

import { AskThread } from "./ask-thread";
import { CitationCard } from "./citation-card";
import { QuotaBanner } from "./quota-banner";
import { extractErrorState } from "./types";

const aiMessages = {
  ai: {
    ask: {
      title: "Ask Vergeo",
      subtitle: "Ask about products, services, and events on Vergeo5.",
      inputLabel: "Your question",
      inputPlaceholder: "e.g. Where can I buy a solar fridge in Lusaka?",
      submit: "Ask",
      submitting: "Thinking",
      emptyHint: "Type a question to search across Vergeo5.",
      citationsTitle: "Related on Vergeo5",
      signupCta: "Sign up",
      networkError: "Couldn't reach Ask Vergeo. Check your connection and try again.",
      viewProduct: "View product",
      viewEvent: "View event",
    },
    quota: {
      guestExceeded: "You've used your free guest questions.",
      monthlyExceeded: "You've reached your monthly question limit.",
      killSwitch: "Ask Vergeo is temporarily unavailable.",
      rateLimited: "Too many questions too quickly.",
      signupPrompt: "Sign up for 25 free questions per month.",
    },
    answer: {
      not_found: "I couldn't find that on Vergeo5.",
      unavailable: "Ask Vergeo is temporarily unavailable shortly.",
    },
    disclaimer: "AI answers are suggestions — verify before you buy",
  },
};

function renderThread(initialQuery = "") {
  return render(
    <NextIntlClientProvider locale="en" messages={aiMessages} onError={() => {}}>
      <AskThread locale="en" initialQuery={initialQuery} />
    </NextIntlClientProvider>,
  );
}

function apiError(details: Record<string, unknown>, code = "ai_quota", message = "err"): ApiError {
  return new ApiError(code, message, { status: 429, details });
}

describe("extractErrorState", () => {
  it("reads quota details.i18n_key and signup_prompt_key", () => {
    const state = extractErrorState(
      apiError({ i18n_key: "ai.quota.guestExceeded", signup_prompt_key: "ai.quota.signupPrompt" }),
    );
    expect(state.messageKey).toBe("ai.quota.guestExceeded");
    expect(state.signupPromptKey).toBe("ai.quota.signupPrompt");
  });

  it("prefers details.message_key for rate-limit envelopes", () => {
    const state = extractErrorState(apiError({ message_key: "ai.quota.rateLimited" }));
    expect(state.messageKey).toBe("ai.quota.rateLimited");
    expect(state.signupPromptKey).toBeNull();
  });

  it("maps network_error code to the network banner", () => {
    const state = extractErrorState(new ApiError("network_error", "boom", { status: 0 }));
    expect(state.messageKey).toBe("ai.ask.networkError");
  });

  it("falls back to unavailable for unkeyed errors", () => {
    const state = extractErrorState(apiError({}, "ask_unavailable", "nope"));
    expect(state.messageKey).toBe("ai.answer.unavailable");
  });
});

describe("QuotaBanner", () => {
  it("renders message only", () => {
    render(<QuotaBanner message="Slow down" />);
    expect(screen.getByTestId("ask-quota-banner")).toHaveTextContent("Slow down");
    expect(screen.queryByTestId("ask-signup-cta")).not.toBeInTheDocument();
  });

  it("renders signup CTA when provided", () => {
    render(
      <QuotaBanner
        message="Out of questions"
        signup={{ prompt: "Get 25 free", ctaLabel: "Sign up", href: "/en/login" }}
      />,
    );
    expect(screen.getByTestId("ask-signup-cta")).toHaveAttribute("href", "/en/login");
  });
});

describe("CitationCard", () => {
  it("links a listing to the product PDP", () => {
    render(
      <CitationCard
        locale="en"
        viewLabel="View product"
        citation={{
          entity_kind: "listing",
          entity_id: "prod-1",
          title: "Solar fridge",
          price_display: "K4,500.00",
        }}
      />,
    );
    const card = screen.getByTestId("ask-citation-card");
    expect(card).toHaveAttribute("href", "/en/p/prod-1");
    expect(card).toHaveAttribute("data-kind", "product");
    expect(card).toHaveTextContent("K4,500.00");
  });

  it("links an event to the event PDP", () => {
    render(
      <CitationCard
        locale="en"
        viewLabel="View event"
        citation={{
          entity_kind: "event",
          entity_id: "evt-9",
          title: "Zed Summer Fest",
          price_display: null,
        }}
      />,
    );
    const card = screen.getByTestId("ask-citation-card");
    expect(card).toHaveAttribute("href", "/en/e/evt-9");
    expect(card).toHaveAttribute("data-kind", "event");
  });
});

describe("AskThread", () => {
  it("renders answer text and maps citations to product/event cards", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce({
      query: "fridge",
      answer: "Line one\nLine two",
      citations: [
        {
          entity_kind: "listing",
          entity_id: "prod-1",
          title: "Solar fridge",
          price_display: "K4,500.00",
        },
        { entity_kind: "event", entity_id: "evt-9", title: "Expo", price_display: null },
      ],
      cached: false,
      refused: false,
      message_key: null,
    });

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "fridge");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-answer")).toBeInTheDocument());
    expect(request).toHaveBeenCalledWith(
      "/ask",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ query: "fridge" }) }),
    );
    const cards = screen.getAllByTestId("ask-citation-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("href", "/en/p/prod-1");
    expect(cards[1]).toHaveAttribute("href", "/en/e/evt-9");
    expect(screen.getByTestId("ask-answer")).toHaveTextContent("AI answers are suggestions");
  });

  it("shows the refusal copy with no citation cards", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce({
      query: "spaceship",
      answer: "I couldn't find that on Vergeo5.",
      citations: [],
      cached: false,
      refused: true,
      message_key: "ai.answer.not_found",
    });

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "spaceship");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-refusal")).toBeInTheDocument());
    expect(screen.getByTestId("ask-refusal")).toHaveTextContent("I couldn't find that on Vergeo5.");
    expect(screen.queryByTestId("ask-citation-card")).not.toBeInTheDocument();
  });

  it("renders the guest-exceeded banner with a signup CTA", async () => {
    const user = userEvent.setup();
    request.mockRejectedValueOnce(
      apiError({ i18n_key: "ai.quota.guestExceeded", signup_prompt_key: "ai.quota.signupPrompt" }),
    );

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "phones");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-quota-banner")).toBeInTheDocument());
    expect(screen.getByTestId("ask-quota-banner")).toHaveTextContent(
      "You've used your free guest questions.",
    );
    expect(screen.getByTestId("ask-signup-cta")).toHaveAttribute("href", "/en/login?next=/en/ask");
  });

  it("renders the rate-limit banner from details.message_key", async () => {
    const user = userEvent.setup();
    request.mockRejectedValueOnce(apiError({ message_key: "ai.quota.rateLimited" }));

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "phones");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-quota-banner")).toBeInTheDocument());
    expect(screen.getByTestId("ask-quota-banner")).toHaveTextContent(
      "Too many questions too quickly.",
    );
    expect(screen.queryByTestId("ask-signup-cta")).not.toBeInTheDocument();
  });

  it("renders the network-error banner when the request rejects with a network error", async () => {
    const user = userEvent.setup();
    request.mockRejectedValueOnce(
      new ApiError("network_error", "Network request failed", { status: 0 }),
    );

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "phones");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-quota-banner")).toBeInTheDocument());
    expect(screen.getByTestId("ask-quota-banner")).toHaveTextContent("Couldn't reach Ask Vergeo.");
  });

  it("auto-submits the seeded ?q= query once", async () => {
    request.mockResolvedValueOnce({
      query: "solar",
      answer: "Here you go",
      citations: [],
      cached: false,
      refused: false,
      message_key: null,
    });

    renderThread("solar");
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(
      "/ask",
      expect.objectContaining({ body: JSON.stringify({ query: "solar" }) }),
    );
  });
});

describe("ZeroResults Ask Vergeo entry", () => {
  it("deep-links the failed query to the ask route", () => {
    render(
      <ZeroResults
        query="zzzz no match"
        locale="en"
        labels={{
          title: "No results",
          suggestionsTitle: "Try",
          categoriesTitle: "Browse",
          suggestionTerms: [],
          categories: [],
          askVergeoTitle: "Ask Vergeo",
          askVergeoTeaser: "Not sure what to search?",
          askVergeoSlotLabel: "Ask Vergeo assistant slot",
        }}
      />,
    );
    expect(screen.getByTestId("ask-vergeo-slot")).toHaveAttribute(
      "href",
      "/en/ask?q=zzzz%20no%20match",
    );
  });
});
