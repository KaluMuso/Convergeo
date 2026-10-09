// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingFlow } from "./_components/onboarding-flow";
import { DEFAULT_DRAFT } from "./_lib/persistence";

const mock = vi.hoisted(() => ({
  userId: "A" as string | null,
  sessionA: { user: { id: "A" }, access_token: "A" },
  sessionB: { user: { id: "B" }, access_token: "B" },
  bootstrap: vi.fn(),
  save: vi.fn(),
  submit: vi.fn(),
  resubmit: vi.fn(),
  upload: vi.fn(),
  router: { push: vi.fn(), replace: vi.fn() },
  t: (key: string) => key,
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session:
      mock.userId === "A"
        ? mock.sessionA
        : mock.userId === "B"
          ? mock.sessionB
          : null,
    loading: false,
  }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => mock.router,
}));
vi.mock("next-intl", () => ({
  useTranslations: () => mock.t,
}));
vi.mock("./_lib/kyc-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./_lib/kyc-client")>()),
  createKycClient: (getToken: () => string | null) => ({
    bootstrapApplication: () => mock.bootstrap(getToken()),
    saveDraft: () => mock.save(getToken()),
    submit: () => mock.submit(getToken()),
    resubmit: () => mock.resubmit(getToken()),
  }),
}));
vi.mock("./_lib/storage", () => ({
  createStorageClient: (getToken: () => string | null) => ({
    signKycUpload: async () => ({ path: "kyc/A/nrc.jpg" }),
    uploadSigned: () => mock.upload(getToken()),
  }),
}));
vi.mock("./_lib/ui", () => ({ Spinner: () => <span>Loading</span> }));
vi.mock("../_components/async-state", () => ({
  VendorErrorState: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("./_components/business-basics-step", () => ({
  BusinessBasicsStep: ({ onContinue }: { onContinue: () => void }) => (
    <div data-testid="business-step">
      <button type="button" onClick={onContinue}>
        Save basics
      </button>
    </div>
  ),
}));
vi.mock("./_components/step-progress", () => ({ StepProgress: () => null }));
vi.mock("./_components/review-step", () => ({
  ReviewStep: () => <div data-testid="review-step" />,
}));
vi.mock("./_components/kyc-docs-step", () => ({
  KycDocsStep: ({
    nrcPath,
    onUpload,
    onNrcUploaded,
    onContinue,
  }: {
    nrcPath: string | null;
    onUpload: (type: "nrc", file: File) => Promise<string>;
    onNrcUploaded: (path: string) => void;
    onContinue: () => void;
  }) => (
    <div data-testid="docs-step">
      <span data-testid="docs-path">{nrcPath ?? "none"}</span>
      <button
        type="button"
        onClick={() => {
          void onUpload(
            "nrc",
            new File(["fake"], "nrc.jpg", { type: "image/jpeg" }),
          )
            .then(onNrcUploaded)
            .catch(() => undefined);
        }}
      >
        Upload
      </button>
      <button type="button" onClick={onContinue}>
        Continue
      </button>
    </div>
  ),
}));

function application(userId: string, status: "draft" | "rejected" = "draft") {
  return {
    vendor_id: `vendor-${userId}`,
    vendor_status: "draft",
    kyc_tier: null,
    kyc_status: status,
    tier: null,
    kyc_record_id: null,
    kyc_record_status: null,
    business_name: `${userId} Shop`,
    business_category: "electronics",
    business_archetype: "registered_retailer",
    momo_phone: null,
    nrc_path: null,
    selfie_path: null,
    rejection_reason: null,
    rejected_docs: null,
    updated_at: "",
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  mock.userId = "A";
  mock.bootstrap
    .mockReset()
    .mockImplementation(async (userId: string) => application(userId));
  mock.save.mockReset();
  mock.submit.mockReset();
  mock.resubmit.mockReset();
  mock.upload.mockReset();
  mock.router.push.mockReset();
  mock.router.replace.mockReset();
  window.localStorage.clear();
});

afterEach(() => cleanup());

describe("mounted onboarding session boundaries", () => {
  it("does not attach A's delayed upload to B after an account switch", async () => {
    const upload = deferred<string>();
    mock.upload.mockImplementation(() => upload.promise);
    const view = render(<OnboardingFlow locale="en" />);
    await screen.findByTestId("docs-step");

    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(mock.upload).toHaveBeenCalledWith("A"));
    mock.userId = "B";
    view.rerender(<OnboardingFlow locale="en" />);
    await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledWith("B"));
    await screen.findByTestId("docs-step");
    expect(screen.getByTestId("docs-path")).toHaveTextContent("none");

    await act(async () => {
      upload.resolve("kyc/A/nrc.jpg");
      await upload.promise;
    });
    expect(screen.getByTestId("docs-path")).toHaveTextContent("none");
    expect(
      window.localStorage.getItem("vergeo5-vendor-onboarding:B"),
    ).not.toContain("kyc/A/nrc.jpg");
  });

  it("does not revive an old A upload after switching A to B to A", async () => {
    const upload = deferred<string>();
    mock.upload.mockImplementation(() => upload.promise);
    const view = render(<OnboardingFlow locale="en" />);
    await screen.findByTestId("docs-step");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(mock.upload).toHaveBeenCalledWith("A"));

    mock.userId = "B";
    view.rerender(<OnboardingFlow locale="en" />);
    await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledWith("B"));
    await screen.findByTestId("docs-step");
    mock.userId = "A";
    view.rerender(<OnboardingFlow locale="en" />);
    await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledTimes(3));
    await screen.findByTestId("docs-step");

    await act(async () => {
      upload.resolve("kyc/A/old-session-nrc.jpg");
      await upload.promise;
    });
    expect(screen.getByTestId("docs-path")).toHaveTextContent("none");
    expect(
      window.localStorage.getItem("vergeo5-vendor-onboarding:A"),
    ).not.toContain("old-session-nrc.jpg");
  });

  it("ignores A's delayed basics save after B starts onboarding", async () => {
    const save = deferred<ReturnType<typeof application>>();
    mock.bootstrap.mockImplementation(async (userId: string) => ({
      ...application(userId),
      business_name: null,
    }));
    mock.save.mockImplementation(() => save.promise);
    const view = render(<OnboardingFlow locale="en" />);
    await screen.findByTestId("business-step");

    fireEvent.click(screen.getByRole("button", { name: "Save basics" }));
    await waitFor(() => expect(mock.save).toHaveBeenCalledWith("A"));
    mock.userId = "B";
    view.rerender(<OnboardingFlow locale="en" />);
    await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledWith("B"));
    await screen.findByTestId("business-step");

    await act(async () => {
      save.resolve(application("A"));
      await save.promise;
    });
    expect(screen.getByTestId("business-step")).toBeInTheDocument();
    expect(screen.queryByTestId("docs-step")).not.toBeInTheDocument();
  });

  it("returns an invalid offline review draft to document validation", async () => {
    mock.bootstrap.mockRejectedValue(new Error("offline"));
    window.localStorage.setItem(
      "vergeo5-vendor-onboarding:A",
      JSON.stringify({
        ...DEFAULT_DRAFT,
        step: 2,
        businessName: "A Shop",
        businessCategory: "electronics",
        businessArchetype: "registered_retailer",
        legalName: "A Shop Ltd",
        momoPhone: "0123456789",
        nrcPath: "kyc/A/nrc.jpg",
        selfiePath: "kyc/A/selfie.jpg",
      }),
    );

    render(<OnboardingFlow locale="en" />);
    await screen.findByTestId("docs-step");
    expect(screen.queryByTestId("review-step")).not.toBeInTheDocument();
  });

  it("rejects invalid phone details before a resubmission call", async () => {
    mock.bootstrap.mockResolvedValue(application("A", "rejected"));
    window.localStorage.setItem(
      "vergeo5-vendor-onboarding:A",
      JSON.stringify({
        ...DEFAULT_DRAFT,
        step: 1,
        businessName: "A Shop",
        businessCategory: "electronics",
        businessArchetype: "registered_retailer",
        legalName: "A Shop Ltd",
        momoPhone: "0123456789",
        nrcPath: "kyc/A/nrc.jpg",
        selfiePath: "kyc/A/selfie.jpg",
      }),
    );
    render(<OnboardingFlow locale="en" />);
    await screen.findByTestId("docs-step");
    expect(screen.getByTestId("docs-path")).toHaveTextContent("kyc/A/nrc.jpg");
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(mock.resubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "onboarding.errors.submitFailed",
    );
  });
});
