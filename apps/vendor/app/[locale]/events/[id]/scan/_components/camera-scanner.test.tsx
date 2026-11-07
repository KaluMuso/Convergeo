import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { CameraScanner } from "./camera-scanner";

const decode = vi.hoisted(() => vi.fn());
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("../../../../scan/_lib/qr-decode", () => ({ decodeQrFromImageData: decode }));
let frames: Map<number, FrameRequestCallback>;
let frameId: number;
const stop = vi.fn();
const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
const getUserMedia = vi.fn();
const detected = vi.fn();
const denied = vi.fn();
function mount(disabled = false) {
  return render(
    <CameraScanner disabled={disabled} onCodeDetected={detected} onCameraDenied={denied} />,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  frames = new Map();
  frameId = 0;
  getUserMedia.mockResolvedValue(stream);
  decode.mockResolvedValue(null);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    frames.set(++frameId, cb);
    return frameId;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("attaches an available stream to a mounted video and becomes active", async () => {
  const view = mount();
  await screen.findByTestId("event-scan-camera-active");
  expect(view.container.querySelector("video")?.srcObject).toBe(stream);
  expect(denied).not.toHaveBeenCalled();
  view.unmount();
  expect(stop).toHaveBeenCalledTimes(1);
  expect(frames.size).toBe(0);
});
it.each(["missing", "denied"])("offers manual fallback when camera is %s", async (kind) => {
  if (kind === "missing") vi.stubGlobal("navigator", {});
  else getUserMedia.mockRejectedValue(new Error("Synthetic permission denial"));
  mount();
  await waitFor(() => expect(denied).toHaveBeenCalledTimes(1));
  expect(screen.getByTestId("event-scan-camera-denied")).toBeVisible();
});
it("stops a permission response arriving after unmount", async () => {
  let resolve!: (stream: MediaStream) => void;
  getUserMedia.mockReturnValue(
    new Promise<MediaStream>((r) => {
      resolve = r;
    }),
  );
  const view = mount();
  view.unmount();
  await act(async () => resolve(stream));
  expect(stop).toHaveBeenCalledTimes(1);
  expect(frames.size).toBe(0);
});
it("does not restart frames after delayed play resolves on an unmounted camera", async () => {
  let resolve!: () => void;
  vi.mocked(HTMLMediaElement.prototype.play).mockReturnValue(
    new Promise<void>((r) => {
      resolve = r;
    }),
  );
  const view = mount();
  await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalled());
  view.unmount();
  await act(async () => resolve());
  expect(frames.size).toBe(0);
  expect(stop).toHaveBeenCalledTimes(1);
});
it("ignores a decode completing after camera shutdown", async () => {
  let resolve!: (value: string) => void;
  decode.mockReturnValue(
    new Promise<string>((r) => {
      resolve = r;
    }),
  );
  vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(2);
  vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(1);
  vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(1);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    drawImage: vi.fn(),
    getImageData: () => ({}),
  } as unknown as CanvasRenderingContext2D);
  const view = mount();
  await screen.findByTestId("event-scan-camera-active");
  const entry = [...frames.entries()][0];
  if (!entry) throw new Error("Expected a scheduled camera frame");
  const [id, cb] = entry;
  frames.delete(id);
  act(() => {
    cb(0);
  });
  expect(decode).toHaveBeenCalledTimes(1);
  view.unmount();
  await act(async () => resolve("synthetic-not-a-ticket"));
  expect(detected).not.toHaveBeenCalled();
  expect(frames.size).toBe(0);
});
it("releases resources on disable and can open again", async () => {
  const view = mount();
  await screen.findByTestId("event-scan-camera-active");
  view.rerender(<CameraScanner disabled onCodeDetected={detected} onCameraDenied={denied} />);
  expect(stop).toHaveBeenCalledTimes(1);
  expect(frames.size).toBe(0);
  view.rerender(
    <CameraScanner disabled={false} onCodeDetected={detected} onCameraDenied={denied} />,
  );
  await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(2));
  view.unmount();
  expect(stop).toHaveBeenCalledTimes(2);
});

it("discards an older permission response after a replacement camera is active", async () => {
  let resolveOld!: (stream: MediaStream) => void;
  const oldStop = vi.fn();
  const oldStream = { getTracks: () => [{ stop: oldStop }] } as unknown as MediaStream;
  getUserMedia.mockReturnValueOnce(
    new Promise<MediaStream>((resolve) => {
      resolveOld = resolve;
    }),
  );
  const view = mount();
  view.rerender(<CameraScanner disabled onCodeDetected={detected} onCameraDenied={denied} />);
  view.rerender(
    <CameraScanner disabled={false} onCodeDetected={detected} onCameraDenied={denied} />,
  );
  await screen.findByTestId("event-scan-camera-active");
  await act(async () => resolveOld(oldStream));
  expect(oldStop).toHaveBeenCalledTimes(1);
  expect(view.container.querySelector("video")?.srcObject).toBe(stream);
  expect(stop).not.toHaveBeenCalled();
  view.unmount();
  expect(stop).toHaveBeenCalledTimes(1);
});

it("releases a stream when playback fails and requests manual fallback", async () => {
  vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValue(
    new Error("Synthetic playback failure"),
  );
  mount();
  await waitFor(() => expect(denied).toHaveBeenCalledTimes(1));
  expect(stop).toHaveBeenCalledTimes(1);
  expect(frames.size).toBe(0);
});
