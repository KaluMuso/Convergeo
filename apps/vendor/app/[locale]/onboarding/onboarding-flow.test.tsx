// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ApiError } from "@vergeo/config";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingFlow } from "./_components/onboarding-flow";
import { DEFAULT_DRAFT, readLocalDraft, writeLocalDraft } from "./_lib/persistence";

import type { KycApplication, KycStatus, OnboardingDraft } from "./_lib/types";

const mock = vi.hoisted(() => ({
  userId: "A" as string | null,
  loading: false,
  sessionA: { user: { id: "A" }, access_token: "A" },
  sessionB: { user: { id: "B" }, access_token: "B" },
  bootstrap: vi.fn(),
  save: vi.fn(),
  submit: vi.fn(),
  resubmit: vi.fn(),
  sign: vi.fn(),
  upload: vi.fn(),
  camera: vi.fn(),
  stopCamera: vi.fn(),
  router: { push: vi.fn(), replace: vi.fn() },
  t: (key: string) => key,
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: mock.userId === "A" ? mock.sessionA : mock.userId === "B" ? mock.sessionB : null,
    loading: mock.loading,
  }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => mock.router }));
vi.mock("next-intl", () => ({ useTranslations: () => mock.t }));
vi.mock("./_lib/kyc-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./_lib/kyc-client")>()),
  createKycClient: (getToken: () => string | null) => ({
    bootstrapApplication: () => mock.bootstrap(getToken()),
    saveDraft: (payload: unknown) => mock.save(getToken(), payload),
    submit: (payload: unknown) => mock.submit(getToken(), payload),
    resubmit: (payload: unknown) => mock.resubmit(getToken(), payload),
  }),
}));
vi.mock("./_lib/storage", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./_lib/storage")>()),
  createStorageClient: (getToken: () => string | null) => ({
    signKycUpload: (type: string, size: number) => mock.sign(getToken(), type, size),
    uploadSigned: (file: File, signed: unknown) => mock.upload(getToken(), file, signed),
  }),
}));

// The forms, document capture, upload state and buttons are real components.
// Auth, network, media streams and canvas output use offline synthetic fixtures.
function application(userId: string, status: KycStatus = "draft"): KycApplication {
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

function completedDraft(userId = "A"): OnboardingDraft {
  return {
    ...DEFAULT_DRAFT,
    step: 2,
    businessName: `${userId} Shop`,
    businessCategory: "electronics",
    businessArchetype: "registered_retailer",
    legalName: `${userId} Shop Ltd`,
    momoPhone: "+260 977 123456",
    nrcPath: `kyc/vendor-${userId}/nrc.jpg`,
    selfiePath: `kyc/vendor-${userId}/selfie.jpg`,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
async function settle<T>(pending: ReturnType<typeof deferred<T>>, value: T, fails = false) {
  await act(async () => {
    if (fails) pending.reject(new Error("offline"));
    else pending.resolve(value);
    await pending.promise.catch(() => undefined);
  });
}
const docsHeading = "onboarding.kyc.heading";
const reviewHeading = "onboarding.review.heading";
const businessHeading = "onboarding.business.heading";
const nrcLabel = "onboarding.kyc.nrcLabel";
async function docs() {
  await screen.findByRole("heading", { name: docsHeading });
}
async function review() {
  await screen.findByRole("heading", { name: reviewHeading });
}
function nrcCaptureElement() {
  return screen.getByText(nrcLabel).parentElement!.parentElement!;
}
function nrcCapture() {
  return within(nrcCaptureElement());
}
async function startPhoto() {
  await act(async () => {
    const button = nrcCapture().getByRole("button", { name: "onboarding.kyc.capture" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
  });
}
async function takeReadyPhoto() {
  await waitFor(() =>
    expect(nrcCaptureElement().querySelector("video")).toHaveAttribute("aria-hidden", "false"),
  );
  fireEvent.click(nrcCapture().getByRole("button", { name: "onboarding.kyc.capture" }));
}
async function confirmPhoto() {
  fireEvent.click(await nrcCapture().findByRole("button", { name: "onboarding.kyc.usePhoto" }));
}
async function selectPhoto() {
  await startPhoto();
  await takeReadyPhoto();
}
async function capture() {
  await selectPhoto();
  await confirmPhoto();
}
function cameraReadiness(stage: "acquisition" | "playback") {
  const ready = deferred<void>();
  if (stage === "acquisition") {
    mock.camera.mockImplementationOnce(async () => {
      await ready.promise;
      return { getTracks: () => [{ stop: mock.stopCamera }] };
    });
  } else {
    vi.mocked(HTMLMediaElement.prototype.play).mockReturnValueOnce(ready.promise);
  }
  return ready;
}
async function renderOfflineDocs() {
  const bootstrap = deferred<KycApplication>();
  mock.bootstrap.mockReturnValueOnce(bootstrap.promise);
  render(<OnboardingFlow locale="en" />);
  await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledOnce());
  // Commit the failed bootstrap and mounted camera effects before interacting.
  await settle(bootstrap, application("A"), true);
  await docs();
  expect(screen.getByText("onboarding.errors.loadFailed")).toBeInTheDocument();
}
async function switchAccount(view: ReturnType<typeof render>, userId: string | null) {
  mock.userId = userId;
  view.rerender(<OnboardingFlow locale="en" />);
  if (userId) await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledWith(userId));
}
function enterBusiness() {
  fireEvent.change(screen.getByLabelText(/^onboarding\.business\.nameLabel/), {
    target: { value: "A Shop" },
  });
  fireEvent.change(screen.getByLabelText(/^onboarding\.business\.categoryLabel/), {
    target: { value: "electronics" },
  });
  fireEvent.change(screen.getByLabelText(/^onboarding\.business\.archetypeLabel/), {
    target: { value: "registered_retailer" },
  });
}
function submitReview() {
  fireEvent.click(screen.getByRole("button", { name: "onboarding.review.submit" }));
}

beforeEach(() => {
  mock.userId = "A";
  mock.loading = false;
  mock.stopCamera.mockReset();
  mock.camera.mockReset().mockResolvedValue({ getTracks: () => [{ stop: mock.stopCamera }] });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: mock.camera } });
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = () => "blob:offline-photo";
    },
  );
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    drawImage: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => {
    callback(new Blob(["fake"], { type: "image/jpeg" }));
  });
  mock.sessionA = { user: { id: "A" }, access_token: "A" };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error("Unexpected live request");
    }),
  );
  mock.bootstrap.mockReset().mockImplementation(async (userId: string) => application(userId));
  mock.save.mockReset().mockImplementation(async (userId: string) => application(userId));
  mock.submit.mockReset().mockResolvedValue({});
  mock.resubmit.mockReset().mockResolvedValue({});
  mock.sign
    .mockReset()
    .mockImplementation(async (userId: string) => ({ path: `kyc/vendor-${userId}/new-nrc.jpg` }));
  mock.upload
    .mockReset()
    .mockImplementation(
      async (_userId: string, _file: File, signed: { path: string }) => signed.path,
    );
  mock.router.push.mockReset();
  mock.router.replace.mockReset();
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("account-scoped mounted onboarding", () => {
  it.each([false, true])(
    "ignores a stale bootstrap (failure=%s), including terminal redirects",
    async (fails) => {
      const pending = deferred<KycApplication>();
      mock.bootstrap.mockImplementation((userId: string) =>
        userId === "A" ? pending.promise : Promise.resolve(application(userId)),
      );
      const view = render(<OnboardingFlow locale="en" />);
      await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledWith("A"));
      await switchAccount(view, "B");
      await docs();
      await settle(pending, application("A", "approved"), fails);
      expect(readLocalDraft("B")?.businessName).toBe("B Shop");
      expect(readLocalDraft("A")).toBeNull();
      expect(mock.router.replace).not.toHaveBeenCalled();
      expect(screen.queryByText("onboarding.errors.loadFailed")).not.toBeInTheDocument();
    },
  );

  it.each(["sign", "upload"] as const)(
    "rejects A's delayed %s before attaching documents to B",
    async (stage) => {
      const pending = deferred<{ path: string } | string>();
      mock[stage].mockImplementation(() => pending.promise);
      const view = render(<OnboardingFlow locale="en" />);
      await docs();
      await capture();
      await waitFor(() => expect(mock[stage]).toHaveBeenCalled());
      await switchAccount(view, "B");
      await docs();
      expect(nrcCapture().queryByAltText("")).not.toBeInTheDocument();
      await settle(
        pending,
        stage === "sign" ? { path: "kyc/vendor-A/late.jpg" } : "kyc/vendor-A/late.jpg",
      );
      expect(readLocalDraft("B")?.nrcPath).toBeNull();
      expect(screen.queryByText("onboarding.kyc.uploadFailed")).not.toBeInTheDocument();
      if (stage === "sign") expect(mock.upload).not.toHaveBeenCalled();
    },
  );

  it("does not revive an old A upload after A → B → A, or clear a newer upload's spinner", async () => {
    const old = deferred<string>();
    const current = deferred<string>();
    mock.upload
      .mockImplementationOnce(() => old.promise)
      .mockImplementationOnce(() => current.promise);
    const view = render(<OnboardingFlow locale="en" />);
    await docs();
    await capture();
    await waitFor(() => expect(mock.upload).toHaveBeenCalledTimes(1));
    await switchAccount(view, "B");
    await docs();
    await switchAccount(view, "A");
    await docs();
    await capture();
    await waitFor(() => expect(mock.upload).toHaveBeenCalledTimes(2));
    await settle(old, "kyc/vendor-A/old-session.jpg");
    expect(readLocalDraft("A")?.nrcPath).toBeNull();
    expect(screen.getByText("onboarding.kyc.uploading")).toBeInTheDocument();
    await settle(current, "kyc/vendor-A/current.jpg");
    expect(readLocalDraft("A")?.nrcPath).toBe("kyc/vendor-A/current.jpg");
  });

  it.each([false, true])(
    "ignores a delayed basics save after an account switch (failure=%s)",
    async (fails) => {
      const pending = deferred<KycApplication>();
      mock.bootstrap.mockImplementation(async (userId: string) => ({
        ...application(userId),
        business_name: null,
      }));
      mock.save.mockImplementation(() => pending.promise);
      const view = render(<OnboardingFlow locale="en" />);
      await screen.findByRole("heading", { name: businessHeading });
      enterBusiness();
      fireEvent.click(screen.getByRole("button", { name: "onboarding.business.continue" }));
      await waitFor(() => expect(mock.save).toHaveBeenCalledTimes(1));
      await switchAccount(view, "B");
      await screen.findByRole("heading", { name: businessHeading });
      await settle(pending, application("A"), fails);
      expect(screen.getByRole("heading", { name: businessHeading })).toBeInTheDocument();
      expect(screen.queryByText("onboarding.errors.saveFailed")).not.toBeInTheDocument();
      expect(readLocalDraft("B")?.businessName).toBe("");
    },
  );

  it.each([
    ["submit", false],
    ["submit", true],
    ["resubmit", false],
    ["resubmit", true],
  ] as const)(
    "ignores stale %s results (failure=%s) and leaves both account drafts intact",
    async (method, fails) => {
      const pending = deferred<unknown>();
      writeLocalDraft("A", completedDraft());
      writeLocalDraft("B", completedDraft("B"));
      mock.bootstrap.mockImplementation(async (id: string) =>
        application(id, method === "resubmit" && id === "A" ? "rejected" : "draft"),
      );
      mock[method].mockImplementation(() => pending.promise);
      const view = render(<OnboardingFlow locale="en" />);
      if (method === "submit") {
        await review();
        submitReview();
      } else {
        await screen.findByRole("heading", { name: "onboarding.status.resubmit.title" });
        fireEvent.click(screen.getByRole("button", { name: "onboarding.status.resubmit.submit" }));
      }
      await waitFor(() => expect(mock[method]).toHaveBeenCalledTimes(1));
      await switchAccount(view, "B");
      await review();
      await settle(pending, {}, fails);
      expect(readLocalDraft("A")).not.toBeNull();
      expect(readLocalDraft("B")).not.toBeNull();
      expect(mock.router.push).not.toHaveBeenCalled();
      expect(screen.queryByText("onboarding.errors.submitFailed")).not.toBeInTheDocument();
    },
  );

  it("does not let an old A submit clear the returning A draft after A → B → A", async () => {
    writeLocalDraft("A", completedDraft());
    const pending = deferred<unknown>();
    mock.submit.mockImplementation(() => pending.promise);
    const view = render(<OnboardingFlow locale="en" />);
    await review();
    submitReview();
    await switchAccount(view, "B");
    await docs();
    await switchAccount(view, "A");
    await review();
    await settle(pending, {});
    expect(readLocalDraft("A")).not.toBeNull();
    expect(mock.router.push).not.toHaveBeenCalled();
  });

  it("discards stale upload errors and capture previews on logout", async () => {
    const pending = deferred<string>();
    mock.upload.mockImplementation(() => pending.promise);
    const view = render(<OnboardingFlow locale="en" />);
    await docs();
    await capture();
    await waitFor(() => expect(mock.upload).toHaveBeenCalled());
    await switchAccount(view, null);
    expect(screen.getByText("onboarding.errors.authRequired")).toBeInTheDocument();
    await settle(pending, "", true);
    await switchAccount(view, "A");
    await docs();
    expect(nrcCapture().queryByAltText("")).not.toBeInTheDocument();
    expect(screen.queryByText("onboarding.kyc.uploadFailed")).not.toBeInTheDocument();
  });
});

describe("resume validation and existing permission policy", () => {
  it.each([
    { momoPhone: "0123456789" },
    { legalName: "A" },
    { nrcPath: null },
    { selfiePath: null },
    { nrcPath: "public/nrc.jpg" },
    { selfiePath: "kyc/../selfie.jpg" },
  ])("returns interrupted offline review to KYC for invalid details: %j", async (patch) => {
    writeLocalDraft("A", { ...completedDraft(), ...patch });
    mock.bootstrap.mockRejectedValue(new Error("offline"));
    render(<OnboardingFlow locale="en" />);
    await docs();
    expect(screen.queryByRole("heading", { name: reviewHeading })).not.toBeInTheDocument();
    expect(mock.submit).not.toHaveBeenCalled();
    expect(mock.resubmit).not.toHaveBeenCalled();
  });

  it("resumes a valid interrupted draft at review and merges server documents", async () => {
    writeLocalDraft("A", { ...completedDraft(), nrcPath: null, selfiePath: null });
    mock.bootstrap.mockResolvedValue({
      ...application("A"),
      nrc_path: "kyc/vendor-A/server-nrc.jpg",
      selfie_path: "kyc/vendor-A/server-selfie.jpg",
    });
    render(<OnboardingFlow locale="en" />);
    await review();
    expect(readLocalDraft("A")?.nrcPath).toBe("kyc/vendor-A/server-nrc.jpg");
    expect(screen.getByTestId("onboarding-invite-banner")).toHaveTextContent(
      "onboarding.invite.body",
    );
    expect(screen.getByText("onboarding.review.gateNotice")).toBeInTheDocument();
  });

  it.each([401, 403])(
    "keeps bootstrap %s fail-closed despite a valid local draft",
    async (status) => {
      writeLocalDraft("A", completedDraft());
      mock.bootstrap.mockRejectedValue(new ApiError("denied", "denied", { status }));
      render(<OnboardingFlow locale="en" />);
      await screen.findByTestId("vendor-error-state");
      expect(screen.queryByRole("heading", { name: reviewHeading })).not.toBeInTheDocument();
      expect(mock.submit).not.toHaveBeenCalled();
    },
  );

  it("prevents invalid rejected details from calling resubmit", async () => {
    writeLocalDraft("A", { ...completedDraft(), momoPhone: "0123456789" });
    mock.bootstrap.mockResolvedValue(application("A", "rejected"));
    render(<OnboardingFlow locale="en" />);
    await screen.findByRole("heading", { name: "onboarding.status.resubmit.title" });
    const button = screen.getByRole("button", { name: "onboarding.status.resubmit.submit" });
    expect(button).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    expect(mock.resubmit).not.toHaveBeenCalled();
  });

  it("preserves terminal routing without submitting again", async () => {
    mock.bootstrap.mockResolvedValue(application("A", "submitted"));
    render(<OnboardingFlow locale="en" />);
    await waitFor(() => expect(mock.router.replace).toHaveBeenCalledWith("/en/onboarding/status"));
    expect(mock.submit).not.toHaveBeenCalled();
  });
});

describe("repeat actions, retry and navigation", () => {
  it.each(["submit", "resubmit"] as const)(
    "sends a repeated %s action only once, including after success",
    async (method) => {
      writeLocalDraft("A", completedDraft());
      writeLocalDraft("B", completedDraft("B"));
      const pending = deferred<unknown>();
      mock[method].mockImplementation(() => pending.promise);
      mock.bootstrap.mockResolvedValue(
        application("A", method === "resubmit" ? "rejected" : "draft"),
      );
      render(<OnboardingFlow locale="en" />);
      const button = await screen.findByRole("button", {
        name:
          method === "resubmit" ? "onboarding.status.resubmit.submit" : "onboarding.review.submit",
      });
      await act(async () => {
        fireEvent.click(button);
        fireEvent.click(button);
      });
      expect(mock[method]).toHaveBeenCalledTimes(1);
      await settle(pending, {});
      fireEvent.click(button);
      expect(mock[method]).toHaveBeenCalledTimes(1);
      expect(mock[method]).toHaveBeenCalledWith(
        "A",
        expect.objectContaining({
          tier: 1,
          momo_phone: "0977123456",
          legal_name: "A Shop Ltd",
          doc_storage_paths: ["kyc/vendor-A/nrc.jpg", "kyc/vendor-A/selfie.jpg"],
          archetype: "electronics",
          business_archetype: "registered_retailer",
        }),
      );
      expect(readLocalDraft("A")).toBeNull();
      expect(readLocalDraft("B")).not.toBeNull();
      expect(mock.router.push).toHaveBeenCalledOnce();
    },
  );

  it("allows retry after a submit failure", async () => {
    writeLocalDraft("A", completedDraft());
    mock.submit.mockRejectedValueOnce(new Error("offline"));
    render(<OnboardingFlow locale="en" />);
    await review();
    submitReview();
    await screen.findByText("onboarding.errors.submitFailed");
    submitReview();
    await waitFor(() => expect(mock.router.push).toHaveBeenCalledOnce());
    expect(mock.submit).toHaveBeenCalledTimes(2);
  });

  it("suppresses repeated basics saves", async () => {
    mock.bootstrap.mockResolvedValue({ ...application("A"), business_name: null });
    const pending = deferred<KycApplication>();
    mock.save.mockImplementation(() => pending.promise);
    render(<OnboardingFlow locale="en" />);
    await screen.findByRole("heading", { name: businessHeading });
    enterBusiness();
    const button = screen.getByRole("button", { name: "onboarding.business.continue" });
    await act(async () => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(mock.save).toHaveBeenCalledOnce();
    await settle(pending, application("A"));
    await docs();
  });

  it.each([false, true])("editing back cancels submit UI effects (failure=%s)", async (fails) => {
    writeLocalDraft("A", completedDraft());
    const pending = deferred<unknown>();
    mock.submit.mockImplementation(() => pending.promise);
    render(<OnboardingFlow locale="en" />);
    await review();
    submitReview();
    fireEvent.click(screen.getByRole("button", { name: "onboarding.review.editDocs" }));
    await docs();
    fireEvent.change(screen.getByLabelText("onboarding.kyc.legalNameLabel"), {
      target: { value: "Changed Ltd" },
    });
    await settle(pending, {}, fails);
    expect(readLocalDraft("A")?.legalName).toBe("Changed Ltd");
    expect(mock.router.push).not.toHaveBeenCalled();
    expect(screen.queryByText("onboarding.errors.submitFailed")).not.toBeInTheDocument();
  });

  it("keeps an in-flight submit locked when editing back and returning to review", async () => {
    writeLocalDraft("A", completedDraft());
    const pending = deferred<unknown>();
    mock.submit.mockImplementation(() => pending.promise);
    render(<OnboardingFlow locale="en" />);
    await review();
    submitReview();
    fireEvent.click(screen.getByRole("button", { name: "onboarding.review.editDocs" }));
    await docs();
    fireEvent.click(screen.getByRole("button", { name: "onboarding.kyc.continue" }));
    await review();
    expect(screen.getByRole("button", { name: "onboarding.review.submitting" })).toBeDisabled();
    expect(mock.submit).toHaveBeenCalledTimes(1);
    await settle(pending, {});
    expect(readLocalDraft("A")).not.toBeNull();
    expect(mock.router.push).not.toHaveBeenCalled();
  });

  it("retakes an unconfirmed photo without signing or uploading", async () => {
    const view = render(<OnboardingFlow locale="en" />);
    await docs();
    await selectPhoto();
    expect(nrcCapture().getByAltText("")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(nrcCapture().getByRole("button", { name: "onboarding.kyc.retake" }));
    });
    expect(nrcCapture().queryByAltText("")).not.toBeInTheDocument();
    expect(mock.camera).toHaveBeenCalledTimes(2);
    expect(mock.sign).not.toHaveBeenCalled();
    expect(mock.upload).not.toHaveBeenCalled();
    view.unmount();
    expect(mock.stopCamera).toHaveBeenCalledTimes(2);
  });

  it("switching accounts stops the current camera and clears an unconfirmed photo", async () => {
    const view = render(<OnboardingFlow locale="en" />);
    await docs();
    await act(async () => {
      fireEvent.click(nrcCapture().getByRole("button", { name: "onboarding.kyc.capture" }));
    });
    await switchAccount(view, "B");
    await docs();
    expect(mock.stopCamera).toHaveBeenCalledOnce();
    expect(nrcCapture().queryByAltText("")).not.toBeInTheDocument();
    expect(mock.sign).not.toHaveBeenCalled();
  });

  it("retrying bootstrap rejects a pending upload and resets upload state", async () => {
    mock.bootstrap.mockRejectedValueOnce(new Error("offline"));
    writeLocalDraft("A", { ...completedDraft(), nrcPath: null });
    const pending = deferred<string>();
    mock.upload.mockImplementation(() => pending.promise);
    render(<OnboardingFlow locale="en" />);
    await docs();
    await capture();
    await waitFor(() => expect(mock.upload).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledTimes(2));
    await docs();
    await settle(pending, "kyc/vendor-A/stale.jpg");
    expect(readLocalDraft("A")?.nrcPath).toBeNull();
    expect(nrcCapture().getByRole("button", { name: "onboarding.kyc.capture" })).toBeEnabled();
  });

  it.each([
    ["delayed", "acquisition"],
    ["delayed", "playback"],
    ["immediate", "acquisition"],
    ["immediate", "playback"],
  ] as const)(
    "retrying bootstrap rejects a pending upload after %s camera %s",
    async (timing, stage) => {
      writeLocalDraft("A", { ...completedDraft(), nrcPath: null });
      const pending = deferred<string>();
      mock.upload.mockImplementation(() => pending.promise);
      const ready = cameraReadiness(stage);
      if (timing === "immediate") ready.resolve(undefined);
      await renderOfflineDocs();
      // Await the dispatch itself; no background capture task or overlapping wait.
      await startPhoto();
      expect(mock.camera).toHaveBeenCalledOnce();
      if (timing === "delayed") {
        expect(nrcCaptureElement().querySelector("video")).toHaveAttribute("aria-hidden", "true");
        expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(stage === "playback" ? 1 : 0);
      }
      expect(mock.sign).not.toHaveBeenCalled();
      expect(mock.upload).not.toHaveBeenCalled();
      await settle(ready, undefined);
      await takeReadyPhoto();
      expect(mock.sign).not.toHaveBeenCalled();
      expect(mock.upload).not.toHaveBeenCalled();
      await confirmPhoto();
      expect(mock.camera).toHaveBeenCalledOnce();
      expect(mock.sign).toHaveBeenCalledOnce();
      await waitFor(() => expect(mock.upload).toHaveBeenCalledOnce());
      fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
      await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledTimes(2));
      await docs();
      await settle(pending, "kyc/vendor-A/stale.jpg");
      expect(readLocalDraft("A")?.nrcPath).toBeNull();
      expect(nrcCapture().getByRole("button", { name: "onboarding.kyc.capture" })).toBeEnabled();
    },
  );

  it.each([
    ["delayed", "acquisition"],
    ["delayed", "playback"],
    ["immediate", "acquisition"],
    ["immediate", "playback"],
  ] as const)(
    "preserves %s camera %s rejection before retry and stale-upload rejection",
    async (timing, stage) => {
      writeLocalDraft("A", { ...completedDraft(), nrcPath: null });
      const pending = deferred<string>();
      mock.upload.mockImplementation(() => pending.promise);
      const ready = timing === "delayed" ? cameraReadiness(stage) : null;
      if (timing === "immediate" && stage === "acquisition") {
        mock.camera.mockRejectedValueOnce(new Error("offline"));
      } else if (timing === "immediate") {
        vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new Error("offline"));
      }
      await renderOfflineDocs();
      await startPhoto();
      expect(mock.camera).toHaveBeenCalledOnce();
      expect(mock.sign).not.toHaveBeenCalled();
      expect(mock.upload).not.toHaveBeenCalled();
      if (ready) await settle(ready, undefined, true);
      expect(
        await screen.findByText("Could not access camera. Check permissions."),
      ).toBeInTheDocument();
      expect(mock.stopCamera).toHaveBeenCalledTimes(stage === "playback" ? 1 : 0);
      expect(nrcCapture().getByRole("button", { name: "onboarding.kyc.capture" })).toBeEnabled();
      await capture();
      expect(mock.camera).toHaveBeenCalledTimes(2);
      expect(
        screen.queryByText("Could not access camera. Check permissions."),
      ).not.toBeInTheDocument();
      await waitFor(() => expect(mock.upload).toHaveBeenCalledOnce());
      fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
      await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledTimes(2));
      await docs();
      await settle(pending, "kyc/vendor-A/stale.jpg");
      expect(readLocalDraft("A")?.nrcPath).toBeNull();
      expect(nrcCapture().getByRole("button", { name: "onboarding.kyc.capture" })).toBeEnabled();
    },
  );

  it("propagates a missing kickoff control before any media or upload action", async () => {
    writeLocalDraft("A", completedDraft());
    render(<OnboardingFlow locale="en" />);
    await review();
    await expect(startPhoto()).rejects.toThrow(nrcLabel);
    expect(mock.camera).not.toHaveBeenCalled();
    expect(mock.sign).not.toHaveBeenCalled();
    expect(mock.upload).not.toHaveBeenCalled();
  });

  it("rejects an old submit after a token refresh starts a new generation", async () => {
    writeLocalDraft("A", completedDraft());
    const pending = deferred<unknown>();
    mock.submit.mockImplementation(() => pending.promise);
    const view = render(<OnboardingFlow locale="en" />);
    await review();
    submitReview();
    mock.sessionA = { ...mock.sessionA, access_token: "A-refreshed" };
    view.rerender(<OnboardingFlow locale="en" />);
    await waitFor(() => expect(mock.bootstrap).toHaveBeenCalledWith("A-refreshed"));
    await review();
    const busy = screen.getByRole("button", { name: "onboarding.review.submitting" });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    expect(mock.submit).toHaveBeenCalledTimes(1);
    await settle(pending, {});
    expect(readLocalDraft("A")).not.toBeNull();
    expect(mock.router.push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "onboarding.review.submit" })).toBeEnabled();
  });

  it.each(["bootstrap", "upload", "submit"] as const)(
    "rejects pending %s results after unmount",
    async (operation) => {
      const pending = deferred<unknown>();
      if (operation === "bootstrap") mock.bootstrap.mockImplementation(() => pending.promise);
      if (operation === "upload") mock.upload.mockImplementation(() => pending.promise);
      if (operation === "submit") {
        writeLocalDraft("A", completedDraft());
        mock.submit.mockImplementation(() => pending.promise);
      }
      const view = render(<OnboardingFlow locale="en" />);
      if (operation === "upload") {
        await docs();
        await capture();
      }
      if (operation === "submit") {
        await review();
        submitReview();
      }
      await waitFor(() => expect(mock[operation]).toHaveBeenCalled());
      const before = window.localStorage.getItem("vergeo5-vendor-onboarding:A");
      view.unmount();
      await settle(
        pending,
        operation === "bootstrap"
          ? application("A", "approved")
          : operation === "upload"
            ? "kyc/vendor-A/late.jpg"
            : {},
      );
      expect(window.localStorage.getItem("vergeo5-vendor-onboarding:A")).toBe(before);
      expect(mock.router.push).not.toHaveBeenCalled();
      expect(mock.router.replace).not.toHaveBeenCalled();
    },
  );

  it("survives StrictMode effect replay without accepting the first bootstrap result", async () => {
    const stale = deferred<KycApplication>();
    mock.bootstrap.mockImplementationOnce(() => stale.promise);
    render(
      <StrictMode>
        <OnboardingFlow locale="en" />
      </StrictMode>,
    );
    await docs();
    await settle(stale, application("A", "approved"));
    expect(mock.router.replace).not.toHaveBeenCalled();
    expect(readLocalDraft("A")?.businessName).toBe("A Shop");
  });
});
