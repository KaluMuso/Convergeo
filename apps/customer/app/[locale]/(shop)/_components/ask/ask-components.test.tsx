// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
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

vi.mock("../../../../../lib/customer-session", () => ({
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
import { QuotaMeter } from "./quota-meter";
import { AskSpeakButton } from "./speak-button";
import { pickVoice } from "./speech-synthesis";
import { extractErrorState, parseQuota } from "./types";
import { AskVoiceButton } from "./voice-button";

const voiceLabels = {
  start: "Speak your question",
  stop: "Stop listening",
  listening: "Listening",
  error: "Couldn't hear that",
  denied: "Microphone is blocked",
};

type FakeRecognition = {
  lang: string;
  onresult: ((event: unknown) => void) | null;
  onend: (() => void) | null;
  start: () => void;
};

function installSpeechRecognition(): { instances: FakeRecognition[] } {
  const instances: FakeRecognition[] = [];
  class FakeSpeechRecognition {
    lang = "";
    continuous = false;
    interimResults = false;
    maxAlternatives = 1;
    onresult: ((event: unknown) => void) | null = null;
    onerror: ((event: unknown) => void) | null = null;
    onend: (() => void) | null = null;
    start = vi.fn();
    stop = vi.fn(() => this.onend?.());
    abort = vi.fn();
    constructor() {
      instances.push(this);
    }
  }
  (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeSpeechRecognition;
  return { instances };
}

function removeSpeechRecognition(): void {
  const speechWindow = window as unknown as Record<string, unknown>;
  delete speechWindow.webkitSpeechRecognition;
  delete speechWindow.SpeechRecognition;
}

afterEach(() => {
  removeSpeechRecognition();
});

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
      viewVendor: "View shop",
      viewService: "View service",
      voiceStart: "Speak your question",
      voiceStop: "Stop listening",
      voiceListening: "Listening",
      voiceError: "Couldn't hear that",
      faqTitle: "Good to know",
      inStock: "In stock",
      outOfStock: "Out of stock",
      distance: "{km} km away",
      useLocation: "Use my location",
      signInCta: "Sign in",
    },
    fallback: {
      aiUnavailable: "Our AI assistant is resting right now.",
      aiPaused: "AI answers are paused for now.",
      resultsTitle: "Top matches",
    },
    intent: {
      price: "{title} costs {price}.",
      nearMeNeedsLocation: "Share your location to see what's near you.",
    },
    faq: {
      cod: {
        q: "Can I pay cash on delivery?",
        a: "Cash on delivery up to K500.",
      },
      escrow: {
        q: "Is my money safe?",
        a: "Held by Vergeo5 until delivery.",
      },
    },
    quota: {
      remainingToday:
        "{count, plural, =0 {No AI questions left today} one {# AI question left today} other {# AI questions left today}}",
      premiumBadge: "Premium",
      guestDailyExceeded: "You've used today's free guest questions.",
      signupPromptDaily: "Sign up for 10 free AI questions a day.",
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
      apiError({
        i18n_key: "ai.quota.guestExceeded",
        signup_prompt_key: "ai.quota.signupPrompt",
      }),
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
        signup={{
          prompt: "Get 25 free",
          ctaLabel: "Sign up",
          href: "/en/login",
        }}
      />,
    );
    expect(screen.getByTestId("ask-signup-cta")).toHaveAttribute("href", "/en/login");
  });
});

describe("CitationCard", () => {
  it("links a listing to the product PDP by slug (never a raw UUID)", () => {
    render(
      <CitationCard
        locale="en"
        viewLabel="View product"
        citation={{
          entity_kind: "listing",
          entity_id: "lst-1",
          title: "Solar fridge",
          price_display: "K4,500.00",
          slug: "solar-fridge",
        }}
      />,
    );
    const card = screen.getByTestId("ask-citation-card");
    expect(card).toHaveAttribute("href", "/en/p/solar-fridge?listing=lst-1");
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
          slug: "zed-summer-fest",
        }}
      />,
    );
    const card = screen.getByTestId("ask-citation-card");
    expect(card).toHaveAttribute("href", "/en/e/zed-summer-fest");
    expect(card).toHaveAttribute("data-kind", "event");
  });
});

describe("CitationCard vendor link", () => {
  const base = {
    entity_kind: "listing",
    entity_id: "lst-1",
    title: "Solar fridge",
    price_display: "K4,500.00",
    slug: "solar-fridge",
    vendor_id: "ven-1",
    vendor_name: "Sun Traders",
    vendor_slug: "sun-traders",
  };

  it("links the item AND its seller, as sibling anchors", () => {
    render(
      <CitationCard
        locale="en"
        viewLabel="View product"
        vendorLabel="Sold by Sun Traders"
        citation={base}
      />,
    );
    const item = screen.getByTestId("ask-citation-card");
    const vendor = screen.getByTestId("ask-citation-vendor");
    expect(item).toHaveAttribute("href", "/en/p/solar-fridge?listing=lst-1");
    expect(vendor).toHaveAttribute("href", "/en/v/sun-traders");
    expect(vendor).toHaveTextContent("Sold by Sun Traders");
    expect(item.contains(vendor)).toBe(false);
  });

  it("links a service to /s and an event to /e, each with its seller", () => {
    const { rerender } = render(
      <CitationCard
        locale="en"
        viewLabel="View service"
        vendorLabel="Sold by Sun Traders"
        citation={{ ...base, entity_kind: "service", entity_id: "svc-1", slug: null }}
      />,
    );
    expect(screen.getByTestId("ask-citation-card")).toHaveAttribute("href", "/en/s/svc-1");
    expect(screen.getByTestId("ask-citation-vendor")).toHaveAttribute("href", "/en/v/sun-traders");

    rerender(
      <CitationCard
        locale="en"
        viewLabel="View event"
        vendorLabel="Sold by Sun Traders"
        citation={{ ...base, entity_kind: "event", entity_id: "evt-1", slug: "expo" }}
      />,
    );
    expect(screen.getByTestId("ask-citation-card")).toHaveAttribute("href", "/en/e/expo");
    expect(screen.getByTestId("ask-citation-vendor")).toHaveAttribute("href", "/en/v/sun-traders");
  });

  it("shows no seller link when the seller is unknown or the card is the vendor", () => {
    const { rerender } = render(
      <CitationCard
        locale="en"
        viewLabel="View product"
        citation={{ ...base, vendor_id: null, vendor_name: null, vendor_slug: null }}
      />,
    );
    expect(screen.queryByTestId("ask-citation-vendor")).toBeNull();

    rerender(
      <CitationCard
        locale="en"
        viewLabel="View shop"
        vendorLabel="Sold by Sun Traders"
        citation={{ ...base, entity_kind: "vendor", entity_id: "ven-1", slug: "sun-traders" }}
      />,
    );
    expect(screen.queryByTestId("ask-citation-vendor")).toBeNull();
    expect(screen.getByTestId("ask-citation-card")).toHaveAttribute("href", "/en/v/sun-traders");
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
          entity_id: "lst-1",
          title: "Solar fridge",
          price_display: "K4,500.00",
          slug: "solar-fridge",
        },
        {
          entity_kind: "event",
          entity_id: "evt-9",
          title: "Expo",
          price_display: null,
          slug: "expo",
        },
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
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "fridge", locale: "en" }),
      }),
    );
    const cards = screen.getAllByTestId("ask-citation-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("href", "/en/p/solar-fridge?listing=lst-1");
    expect(cards[1]).toHaveAttribute("href", "/en/e/expo");
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
      apiError({
        i18n_key: "ai.quota.guestExceeded",
        signup_prompt_key: "ai.quota.signupPrompt",
      }),
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
      expect.objectContaining({ body: JSON.stringify({ query: "solar", locale: "en" }) }),
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

describe("AskVoiceButton", () => {
  it("renders nothing when the Web Speech API is unsupported", () => {
    removeSpeechRecognition();
    const { container } = render(<AskVoiceButton labels={voiceLabels} onTranscript={() => {}} />);
    expect(screen.queryByTestId("ask-voice-button")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the mic when supported and streams an en-* transcript", async () => {
    const { instances } = installSpeechRecognition();
    const onTranscript = vi.fn();
    const user = userEvent.setup();
    render(<AskVoiceButton labels={voiceLabels} onTranscript={onTranscript} />);

    const button = await screen.findByTestId("ask-voice-button");
    expect(button).toHaveAccessibleName("Speak your question");
    await user.click(button);

    await waitFor(() => expect(instances).toHaveLength(1));
    const recognition = instances[0]!;
    expect(recognition.start).toHaveBeenCalled();
    expect(["en-GB", "en-US"]).toContain(recognition.lang);
    expect(screen.getByTestId("ask-voice-button")).toHaveAttribute("aria-pressed", "true");

    recognition.onresult?.({
      resultIndex: 0,
      results: {
        length: 1,
        0: { isFinal: true, length: 1, 0: { transcript: " cheapest phone " } },
      },
    });
    expect(onTranscript).toHaveBeenCalledWith("cheapest phone", true);
  });

  it("tells the user when the microphone is blocked instead of doing nothing", async () => {
    const { instances } = installSpeechRecognition();
    const user = userEvent.setup();
    render(<AskVoiceButton labels={voiceLabels} onTranscript={() => {}} />);
    await user.click(await screen.findByTestId("ask-voice-button"));
    await waitFor(() => expect(instances).toHaveLength(1));
    act(() => {
      (instances[0] as unknown as { onerror: (e: unknown) => void }).onerror({
        error: "not-allowed",
      });
    });
    expect(screen.getByTestId("ask-voice-status")).toHaveTextContent("Microphone is blocked");
  });

  it("shows the generic message for other errors", async () => {
    const { instances } = installSpeechRecognition();
    const user = userEvent.setup();
    render(<AskVoiceButton labels={voiceLabels} onTranscript={() => {}} />);
    await user.click(await screen.findByTestId("ask-voice-button"));
    await waitFor(() => expect(instances).toHaveLength(1));
    act(() => {
      (instances[0] as unknown as { onerror: (e: unknown) => void }).onerror({ error: "network" });
    });
    expect(screen.getByTestId("ask-voice-status")).toHaveTextContent("Couldn't hear that");
  });

  it("is mounted beside the Ask input only when supported", async () => {
    renderThread();
    expect(screen.queryByTestId("ask-voice-button")).not.toBeInTheDocument();
    cleanup();

    installSpeechRecognition();
    renderThread();
    expect(await screen.findByTestId("ask-voice-button")).toBeInTheDocument();
  });
});

describe("Quota display", () => {
  it("QuotaMeter renders the remaining label and tier", () => {
    render(
      <QuotaMeter
        quota={{ tier: "premium", daily_limit: 100, used: 1, remaining: 99 }}
        label="99 AI questions left today"
        premiumLabel="Premium"
      />,
    );
    const meter = screen.getByTestId("ask-quota-meter");
    expect(meter).toHaveTextContent("99 AI questions left today");
    expect(meter).toHaveTextContent("Premium");
    expect(meter).toHaveAttribute("data-remaining", "99");
  });

  it("parseQuota rejects malformed payloads", () => {
    expect(parseQuota(null)).toBeNull();
    expect(parseQuota({ tier: "guest", daily_limit: "3" })).toBeNull();
    expect(parseQuota({ tier: "guest", daily_limit: 3, used: 4, remaining: -1 })).toEqual({
      tier: "guest",
      daily_limit: 3,
      used: 4,
      remaining: 0,
    });
  });

  it("AskThread shows remaining questions from the API response", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce({
      query: "phones",
      answer: "Here are phones.",
      citations: [],
      cached: false,
      refused: false,
      message_key: null,
      source: "ai",
      quota: { tier: "guest", daily_limit: 3, used: 1, remaining: 2 },
    });

    renderThread();
    expect(screen.queryByTestId("ask-quota-meter")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Your question"), "phones");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-quota-meter")).toBeInTheDocument());
    expect(screen.getByTestId("ask-quota-meter")).toHaveTextContent("2 AI questions left today");
  });
});

describe("Workflow + fallback rendering", () => {
  it("renders a workflow answer from its i18n key and params", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce({
      query: "how much is the itel a70",
      answer: "Itel A70 costs K4,500.00.",
      citations: [
        {
          entity_kind: "listing",
          entity_id: "lst-1",
          title: "Itel A70",
          price_display: "K4,500.00",
          slug: "itel-a70",
          in_stock: true,
        },
      ],
      cached: false,
      refused: false,
      message_key: null,
      source: "workflow",
      intent: "price_stock",
      answer_key: "ai.intent.price",
      answer_params: { title: "Itel A70", price: "K4,500.00" },
    });

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "how much is the itel a70");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-answer")).toBeInTheDocument());
    expect(screen.getByTestId("ask-answer")).toHaveAttribute("data-source", "workflow");
    expect(screen.getByTestId("ask-answer")).toHaveTextContent("Itel A70 costs K4,500.00.");
    expect(screen.getByTestId("ask-citation-card")).toHaveTextContent("In stock");
    // Disclaimer is only for model-written answers.
    expect(screen.getByTestId("ask-answer")).not.toHaveTextContent("AI answers are suggestions");
  });

  it("renders the AI-unavailable fallback: note, ranked results and FAQ", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce({
      query: "phone cash on delivery",
      answer: "Here are the closest matches on Vergeo5.",
      citations: [
        {
          entity_kind: "listing",
          entity_id: "lst-1",
          title: "Itel A70",
          price_display: "K4,500.00",
          slug: "itel-a70",
        },
        {
          entity_kind: "vendor",
          entity_id: "ven-1",
          title: "Kabwata Phones",
          price_display: null,
          slug: "kabwata-phones",
        },
      ],
      cached: false,
      refused: false,
      message_key: null,
      source: "fallback",
      notice_key: "ai.fallback.aiUnavailable",
      faq: [{ id: "cod", question_key: "ai.faq.cod.q", answer_key: "ai.faq.cod.a" }],
      quota: { tier: "guest", daily_limit: 3, used: 0, remaining: 3 },
    });

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "phone cash on delivery");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-answer")).toBeInTheDocument());
    expect(screen.getByTestId("ask-quota-banner")).toHaveTextContent(
      "Our AI assistant is resting right now.",
    );
    expect(screen.getByText("Top matches")).toBeInTheDocument();
    const cards = screen.getAllByTestId("ask-citation-card");
    expect(cards).toHaveLength(2);
    expect(cards[1]).toHaveAttribute("href", "/en/v/kabwata-phones");
    expect(screen.getByTestId("ask-faq")).toHaveTextContent("Can I pay cash on delivery?");
    expect(screen.getByTestId("ask-faq")).toHaveTextContent("Cash on delivery up to K500.");
    // The fallback note replaces the model text; no AI disclaimer.
    expect(screen.getByTestId("ask-answer")).not.toHaveTextContent("closest matches on Vergeo5");
    expect(screen.getByTestId("ask-answer")).not.toHaveTextContent("AI answers are suggestions");
  });

  it("renders the guest daily-quota fallback with a signup CTA", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce({
      query: "phones",
      answer: "Here are the closest matches on Vergeo5.",
      citations: [],
      cached: false,
      refused: false,
      message_key: null,
      source: "fallback",
      notice_key: "ai.quota.guestDailyExceeded",
      signup_prompt_key: "ai.quota.signupPromptDaily",
      quota: { tier: "guest", daily_limit: 3, used: 3, remaining: 0 },
    });

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "phones");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByTestId("ask-signup-cta")).toBeInTheDocument());
    expect(screen.getByTestId("ask-quota-banner")).toHaveTextContent(
      "You've used today's free guest questions.",
    );
    expect(screen.getByTestId("ask-quota-meter")).toHaveTextContent("No AI questions left today");
  });

  it("offers 'Use my location' for near-me questions and re-asks with rounded coords", async () => {
    const user = userEvent.setup();
    const getCurrentPosition = vi.fn((success: PositionCallback) =>
      success({
        coords: { latitude: -15.416712, longitude: 28.283321 },
      } as GeolocationPosition),
    );
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition },
    });
    request
      .mockResolvedValueOnce({
        query: "phones near me",
        answer: "Share your location.",
        citations: [],
        cached: false,
        refused: false,
        message_key: null,
        source: "workflow",
        answer_key: "ai.intent.nearMeNeedsLocation",
        needs_location: true,
      })
      .mockResolvedValueOnce({
        query: "phones near me",
        answer: "Closest matches.",
        citations: [],
        cached: false,
        refused: false,
        message_key: null,
        source: "workflow",
      });

    renderThread();
    await user.type(screen.getByLabelText("Your question"), "phones near me");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await user.click(await screen.findByTestId("ask-use-location"));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(request).toHaveBeenLastCalledWith(
      "/ask",
      expect.objectContaining({
        body: JSON.stringify({
          query: "phones near me",
          locale: "en",
          lat: -15.417,
          lng: 28.283,
        }),
      }),
    );
  });
});

type FakeVoice = { lang: string; name: string };

function installSpeechSynthesis(voices: FakeVoice[] = []) {
  const utterances: Array<{
    text: string;
    lang: string;
    voice: FakeVoice | null;
    onend: (() => void) | null;
    onerror: (() => void) | null;
  }> = [];
  class FakeUtterance {
    lang = "";
    voice: FakeVoice | null = null;
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public text: string) {
      utterances.push(this);
    }
  }
  const synth = {
    speak: vi.fn(),
    cancel: vi.fn(),
    getVoices: vi.fn(() => voices),
  };
  Object.assign(window, { speechSynthesis: synth, SpeechSynthesisUtterance: FakeUtterance });
  return { synth, utterances };
}

function removeSpeechSynthesis() {
  const w = window as unknown as Record<string, unknown>;
  delete w.speechSynthesis;
  delete w.SpeechSynthesisUtterance;
}

const speakLabels = { speak: "Read the answer aloud", stop: "Stop reading" };

describe("AskSpeakButton", () => {
  afterEach(() => removeSpeechSynthesis());

  it("renders nothing when speechSynthesis is unsupported", () => {
    removeSpeechSynthesis();
    const { container } = render(<AskSpeakButton text="Hello" locale="en" labels={speakLabels} />);
    expect(screen.queryByTestId("ask-speak-button")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("speaks the answer with a voice for the page locale and toggles to stop", async () => {
    const { synth, utterances } = installSpeechSynthesis([
      { lang: "en-GB", name: "English" },
      { lang: "fr-FR", name: "Francais" },
    ]);
    const user = userEvent.setup();
    render(<AskSpeakButton text="Bonjour" locale="fr" labels={speakLabels} />);

    const button = await screen.findByTestId("ask-speak-button");
    expect(button).toHaveAccessibleName("Read the answer aloud");
    await user.click(button);

    expect(synth.speak).toHaveBeenCalledTimes(1);
    expect(utterances[0]).toMatchObject({ text: "Bonjour", lang: "fr-FR" });
    expect(utterances[0]?.voice?.name).toBe("Francais");
    expect(screen.getByTestId("ask-speak-button")).toHaveAccessibleName("Stop reading");

    synth.cancel.mockClear();
    await user.click(screen.getByTestId("ask-speak-button"));
    expect(synth.cancel).toHaveBeenCalled();
    expect(screen.getByTestId("ask-speak-button")).toHaveAccessibleName("Read the answer aloud");
  });

  it("falls back to English for bem/nya and when no voice matches", async () => {
    const { utterances } = installSpeechSynthesis([{ lang: "en-US", name: "US" }]);
    const user = userEvent.setup();
    render(<AskSpeakButton text="Mwapoleni" locale="bem" labels={speakLabels} />);
    await user.click(await screen.findByTestId("ask-speak-button"));
    expect(utterances[0]?.voice?.name).toBe("US");
    expect(utterances[0]?.lang).toBe("en-US");
    expect(pickVoice([{ lang: "de-DE", name: "De" } as SpeechSynthesisVoice], "fr")).toBeNull();
  });

  it("resets when the utterance ends", async () => {
    const { utterances } = installSpeechSynthesis();
    const user = userEvent.setup();
    render(<AskSpeakButton text="Hi" locale="en" labels={speakLabels} />);
    await user.click(await screen.findByTestId("ask-speak-button"));
    act(() => utterances[0]?.onend?.());
    expect(screen.getByTestId("ask-speak-button")).toHaveAttribute("data-state", "idle");
  });

  it("cancels speech on unmount and when the answer changes", async () => {
    const { synth } = installSpeechSynthesis();
    const user = userEvent.setup();
    const view = render(<AskSpeakButton text="One" locale="en" labels={speakLabels} />);
    await user.click(await screen.findByTestId("ask-speak-button"));
    synth.cancel.mockClear();

    view.rerender(<AskSpeakButton text="Two" locale="en" labels={speakLabels} />);
    expect(synth.cancel).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("ask-speak-button")).toHaveAttribute("data-state", "idle");

    await user.click(screen.getByTestId("ask-speak-button"));
    synth.cancel.mockClear();
    view.unmount();
    expect(synth.cancel).toHaveBeenCalledTimes(1);
  });
});

describe("AskThread read-aloud", () => {
  afterEach(() => removeSpeechSynthesis());

  it("shows a speaker button on a text answer when supported", async () => {
    installSpeechSynthesis();
    request.mockResolvedValueOnce({
      query: "fridge",
      answer: "A fridge answer",
      citations: [],
      cached: false,
      refused: false,
      message_key: null,
    });
    const user = userEvent.setup();
    renderThread();
    await user.type(screen.getByLabelText("Your question"), "fridge");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByTestId("ask-speak-button")).toBeInTheDocument();
  });
});
