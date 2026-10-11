import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  session: { access_token: "local-mocked-token" },
  loading: false,
}));
vi.mock("@vergeo/auth/use-session", () => ({ useSession: () => auth }));
vi.mock("@vergeo/i18n", () => ({ formatK: (ngwee: number) => String(ngwee) }));
vi.mock("next-intl", async () => {
  const { default: messages } =
    await import("../../../../../../packages/i18n/messages/en/vendor.json");
  return {
    useTranslations: () => (key: string) => {
      let value: unknown = messages;
      for (const part of key.split(".")) value = (value as Record<string, unknown>)[part];
      if (typeof value !== "string") throw new Error(`Missing translation: ${key}`);
      return value;
    },
  };
});

import { IntakeReview } from "./intake-review";

const productId = "12345678-1234-4234-8234-123456789abc";
const sessionId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const initialDetail = {
  id: sessionId,
  status: "ready_for_vendor_review",
  listing_id: null,
  draft: {
    title: "Samsung RT38 Fridge",
    category_id: null,
    price_ngwee: 350000,
    condition: "new",
    description: "New Samsung fridge",
    sale_unit: "each",
  },
  provenance: [],
  media: [],
  pending_requests: [],
  missing_fields: [],
  submittable: true,
};

let detail = structuredClone(initialDetail);
let submitError: string | null = null;
let previewUnavailable = false;
const requests: Array<{ path: string; method: string; body: unknown }> = [];
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  detail = structuredClone(initialDetail);
  submitError = null;
  previewUnavailable = false;
  requests.length = 0;
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://127.0.0.1:9876");
  vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "development");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      requests.push({ path, method, body });
      if (path === "/search/suggest")
        return json({
          suggestions: [
            {
              title: "Samsung RT38 Fridge",
              entity_kind: "product",
              entity_id: productId,
            },
          ],
        });
      if (path === `/vendor/listings/canonical/${productId}`) {
        if (previewUnavailable)
          return json(
            {
              error: {
                code: "product_not_attachable",
                message: "Unavailable",
                request_id: "local",
              },
            },
            422,
          );
        return json({
          product_id: productId,
          name: "Samsung RT38 Fridge",
          brand: "Samsung",
          spec: { model: "RT38" },
          category_id: "appliances",
          category_name: "Appliances",
        });
      }
      if (path === `/vendor/intake/sessions/${sessionId}/draft` && method === "PATCH") {
        detail = { ...detail, draft: { ...detail.draft, ...body } };
        return json(detail);
      }
      if (path === `/vendor/intake/sessions/${sessionId}/submit` && method === "POST") {
        if (submitError)
          return json(
            {
              error: {
                code: "intake_draft_not_submittable",
                message: "Invalid",
                request_id: "local",
                details: { message_key: `vendor.intake.errors.${submitError}` },
              },
            },
            422,
          );
        return json({ listing_id: "listing", listing_status: "draft" });
      }
      if (path === `/vendor/intake/sessions/${sessionId}` && method === "GET") return json(detail);
      throw new Error(`NETWORK_BLOCKED: unexpected request ${method} ${path}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

async function openReview() {
  render(<IntakeReview locale="en" sessionId={sessionId} />);
  await screen.findByRole("button", { name: "Submit for review" });
}

async function selectCanonical() {
  const search = screen.getByRole("textbox", {
    name: "Search catalog products",
  });
  fireEvent.change(search, { target: { value: "Samsung" } });
  const result = await screen.findByRole("option", {
    name: "Samsung RT38 Fridge",
  });
  await userEvent.click(result);
  await screen.findByTestId("intake-canonical-preview");
}

describe("explicit canonical intake", () => {
  it("does not choose a name match or submit on load", async () => {
    await openReview();
    fireEvent.change(screen.getByRole("textbox", { name: "Search catalog products" }), {
      target: { value: "Samsung" },
    });
    await screen.findByRole("option", { name: "Samsung RT38 Fridge" });
    expect(screen.getByTestId("intake-submit")).toBeDisabled();
    expect(requests.filter((request) => request.method === "POST")).toEqual([]);
    expect(requests.some((request) => request.path.includes("/canonical/"))).toBe(false);
  });

  it("previews the human selection and submits only its ID on an explicit click", async () => {
    await openReview();
    await selectCanonical();
    expect(screen.getByTestId("intake-canonical-preview")).toHaveTextContent("RT38");
    expect(requests.filter((request) => request.method === "POST")).toEqual([]);
    await userEvent.click(screen.getByTestId("intake-submit"));
    await waitFor(() =>
      expect(requests.filter((request) => request.method === "POST")).toEqual([
        {
          path: `/vendor/intake/sessions/${sessionId}/submit`,
          method: "POST",
          body: { product_id: productId },
        },
      ]),
    );
  });

  it("blocks unsaved money edits, saves exact ngwee and requires selection again", async () => {
    await openReview();
    await selectCanonical();
    fireEvent.change(screen.getByLabelText("Price"), {
      target: { value: "1000.05" },
    });
    expect(screen.getByTestId("intake-submit")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(requests.some((request) => request.method === "PATCH")).toBe(true));
    expect(requests.find((request) => request.method === "PATCH")?.body).toMatchObject({
      price_ngwee: 100005,
    });
    await waitFor(() => expect(screen.queryByTestId("intake-canonical-preview")).toBeNull());
    expect(screen.getByTestId("intake-submit")).toBeDisabled();
  });

  it("clears canonical selection after an identity correction and after reload", async () => {
    await openReview();
    await selectCanonical();
    fireEvent.change(screen.getByLabelText("Product name"), {
      target: { value: "Different model" },
    });
    await waitFor(() => expect(screen.queryByTestId("intake-canonical-preview")).toBeNull());
    expect(screen.getByTestId("intake-submit")).toBeDisabled();
    cleanup();
    await openReview();
    expect(screen.queryByTestId("intake-canonical-preview")).toBeNull();
    expect(screen.getByTestId("intake-submit")).toBeDisabled();
  });

  it("keeps unavailable products unselected and shows a recovery message", async () => {
    previewUnavailable = true;
    await openReview();
    fireEvent.change(screen.getByRole("textbox", { name: "Search catalog products" }), {
      target: { value: "Samsung" },
    });
    await userEvent.click(await screen.findByRole("option", { name: "Samsung RT38 Fridge" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Select an active catalog product");
    expect(screen.getByTestId("intake-submit")).toBeDisabled();
  });

  it("shows clear server validation for unsupported classes", async () => {
    submitError = "unsupportedClass";
    await openReview();
    await selectCanonical();
    await userEvent.click(screen.getByTestId("intake-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Class A branded items only");
  });
});
