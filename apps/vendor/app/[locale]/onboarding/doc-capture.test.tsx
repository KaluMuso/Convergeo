// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocCapture } from "./_components/doc-capture";

const acquire = vi.fn();
const onCapture = vi.fn();
const createPreview = vi.fn();
const drawImage = vi.fn();
let canvasCallbacks: BlobCallback[];
const props = {
  label: "Document",
  helpText: "Synthetic fixture",
  captureLabel: "Capture",
  retakeLabel: "Retake",
  usePhotoLabel: "Confirm",
  onCapture,
};

function fakeStream() {
  const tracks = [0, 1].map(() => {
    const track = { readyState: "live", stop: vi.fn() };
    track.stop.mockImplementation(() => {
      track.readyState = "ended";
    });
    return track;
  });
  return { stream: { getTracks: () => tracks } as unknown as MediaStream, tracks };
}
function expectStopped(fake: ReturnType<typeof fakeStream>, times = 1) {
  for (const track of fake.tracks) {
    expect(track.stop).toHaveBeenCalledTimes(times);
    expect(track.readyState).toBe(times ? "ended" : "live");
  }
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
    if (fails) pending.reject(new Error("synthetic denial"));
    else pending.resolve(value);
    await pending.promise.catch(() => undefined);
  });
}
async function start() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Capture" }));
  });
}
function takePhoto() {
  fireEvent.click(screen.getByRole("button", { name: "Capture" }));
}
async function encode(index = 0, blob: Blob | null = new Blob(["fake"], { type: "image/jpeg" })) {
  await act(async () => {
    canvasCallbacks[index]!(blob);
  });
}
function video(view: ReturnType<typeof render>) {
  return view.container.querySelector("video")!;
}

beforeEach(() => {
  acquire.mockReset();
  onCapture.mockReset();
  createPreview.mockReset().mockReturnValue("blob:synthetic");
  drawImage.mockReset();
  canvasCallbacks = [];
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: acquire } });
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = createPreview;
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error("Unexpected provider request");
    }),
  );
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    drawImage,
  } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => {
    canvasCallbacks.push(callback);
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("normal document capture and existing controls", () => {
  it("keeps camera constraints and JPEG capture, and confirms a photo once", async () => {
    const fake = fakeStream();
    acquire.mockResolvedValue(fake.stream);
    const view = render(<DocCapture {...props} facingMode="user" />);
    await start();
    expect(acquire).toHaveBeenCalledWith({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    expect(video(view).srcObject).toBe(fake.stream);
    const element = video(view);
    takePhoto();
    expect(drawImage).toHaveBeenCalledWith(element, 0, 0, 640, 480);
    expect(HTMLCanvasElement.prototype.toBlob).toHaveBeenCalledWith(
      expect.any(Function),
      "image/jpeg",
      0.85,
    );
    await encode();
    expectStopped(fake);
    expect(element.srcObject).toBeNull();
    expect(screen.getByAltText("")).toHaveAttribute("src", "blob:synthetic");
    const confirm = screen.getByRole("button", { name: "Confirm" });
    await act(async () => {
      fireEvent.click(confirm);
      fireEvent.click(confirm);
    });
    expect(onCapture).toHaveBeenCalledTimes(1);
    const file = onCapture.mock.calls[0]![0] as File;
    expect(file).toBeInstanceOf(File);
    expect(file.type).toBe("image/jpeg");
    expect(file.size).toBe(4);
    expect(file.name).toMatch(/^capture-\d+\.jpg$/);
    view.unmount();
    expectStopped(fake);
  });

  it("does not acquire a camera while disabled", async () => {
    render(<DocCapture {...props} disabled />);
    expect(screen.getByRole("button", { name: "Capture" })).toBeDisabled();
    await start();
    expect(acquire).not.toHaveBeenCalled();
    expect(onCapture).not.toHaveBeenCalled();
  });

  it("preserves the missing-camera error", async () => {
    vi.stubGlobal("navigator", {});
    render(<DocCapture {...props} />);
    await start();
    expect(screen.getByText("Camera not available on this device.")).toBeInTheDocument();
    expect(acquire).not.toHaveBeenCalled();
  });

  it("preserves a current permission rejection and permits another attempt", async () => {
    const fake = fakeStream();
    acquire.mockRejectedValueOnce(new Error("denied")).mockResolvedValueOnce(fake.stream);
    const view = render(<DocCapture {...props} />);
    await start();
    expect(screen.getByText("Could not access camera. Check permissions.")).toBeInTheDocument();
    await start();
    expect(video(view).srcObject).toBe(fake.stream);
    expect(
      screen.queryByText("Could not access camera. Check permissions."),
    ).not.toBeInTheDocument();
  });

  it("retakes a pending photo without confirming the old file", async () => {
    const first = fakeStream();
    const next = fakeStream();
    acquire.mockResolvedValueOnce(first.stream).mockResolvedValueOnce(next.stream);
    const view = render(<DocCapture {...props} />);
    await start();
    takePhoto();
    await encode();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Retake" }));
    });
    expectStopped(first);
    expectStopped(next, 0);
    expect(video(view).srcObject).toBe(next.stream);
    expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    expect(onCapture).not.toHaveBeenCalled();
    takePhoto();
    await encode(1);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onCapture).toHaveBeenCalledTimes(1);
    expectStopped(next);
  });
});

describe("camera acquisition ownership", () => {
  it("stops all acquired tracks once on unmount and detaches the video", async () => {
    const fake = fakeStream();
    acquire.mockResolvedValue(fake.stream);
    const view = render(<DocCapture {...props} />);
    await start();
    const element = video(view);
    view.unmount();
    expectStopped(fake);
    expect(element.srcObject).toBeNull();
  });

  it.each([false, true])("rejects acquisition after unmount (failure=%s)", async (fails) => {
    const pending = deferred<MediaStream>();
    const fake = fakeStream();
    acquire.mockReturnValue(pending.promise);
    const view = render(<DocCapture {...props} />);
    await start();
    view.unmount();
    await settle(pending, fake.stream, fails);
    expectStopped(fake, fails ? 0 : 1);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(createPreview).not.toHaveBeenCalled();
    expect(onCapture).not.toHaveBeenCalled();
  });

  it("releases old A acquisition through A → B → A without stopping current A", async () => {
    const pendingA = deferred<MediaStream>();
    const oldA = fakeStream();
    const b = fakeStream();
    const currentA = fakeStream();
    acquire
      .mockReturnValueOnce(pendingA.promise)
      .mockResolvedValueOnce(b.stream)
      .mockResolvedValueOnce(currentA.stream);
    const view = render(<DocCapture key="A" {...props} />);
    await start();
    view.rerender(<DocCapture key="B" {...props} />);
    await start();
    view.rerender(<DocCapture key="A" {...props} />);
    await start();
    expectStopped(b);
    expectStopped(currentA, 0);
    await settle(pendingA, oldA.stream);
    expectStopped(oldA);
    expectStopped(currentA, 0);
    expect(video(view).srcObject).toBe(currentA.stream);
    expect(onCapture).not.toHaveBeenCalled();
    view.unmount();
    expectStopped(currentA);
  });

  it.each(["older first", "newer first"])(
    "owns only the latest overlapping acquisition (%s)",
    async (order) => {
      const old = deferred<MediaStream>();
      const next = deferred<MediaStream>();
      const oldStream = fakeStream();
      const newStream = fakeStream();
      acquire.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
      const view = render(<DocCapture {...props} />);
      await start();
      await start();
      if (order === "older first") {
        await settle(old, oldStream.stream);
        await settle(next, newStream.stream);
      } else {
        await settle(next, newStream.stream);
        await settle(old, oldStream.stream);
      }
      expectStopped(oldStream);
      expectStopped(newStream, 0);
      expect(video(view).srcObject).toBe(newStream.stream);
      expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
      expect(
        screen.queryByText("Could not access camera. Check permissions."),
      ).not.toBeInTheDocument();
      view.unmount();
      expectStopped(newStream);
    },
  );

  it("releases an older result when the newest acquisition has already failed", async () => {
    const old = deferred<MediaStream>();
    const next = deferred<MediaStream>();
    const oldStream = fakeStream();
    acquire.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
    const view = render(<DocCapture {...props} />);
    await start();
    await start();
    await settle(next, oldStream.stream, true);
    await settle(old, oldStream.stream);
    expectStopped(oldStream);
    expect(video(view).srcObject ?? null).toBeNull();
    expect(video(view)).toHaveAttribute("aria-hidden", "true");
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(screen.getByText("Could not access camera. Check permissions.")).toBeInTheDocument();
    expect(onCapture).not.toHaveBeenCalled();
  });

  it("does not render an old acquisition rejection over a working replacement", async () => {
    const old = deferred<MediaStream>();
    const current = fakeStream();
    acquire.mockReturnValueOnce(old.promise).mockResolvedValueOnce(current.stream);
    const view = render(<DocCapture {...props} />);
    await start();
    await start();
    await settle(old, current.stream, true);
    expectStopped(current, 0);
    expect(video(view).srcObject).toBe(current.stream);
    expect(
      screen.queryByText("Could not access camera. Check permissions."),
    ).not.toBeInTheDocument();
  });
});

describe("playback ownership", () => {
  it("releases a current stream on playback failure and allows retry", async () => {
    const failed = fakeStream();
    const next = fakeStream();
    acquire.mockResolvedValueOnce(failed.stream).mockResolvedValueOnce(next.stream);
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new Error("play failed"));
    const view = render(<DocCapture {...props} />);
    await start();
    expectStopped(failed);
    expect(video(view).srcObject).toBeNull();
    expect(screen.getByText("Could not access camera. Check permissions.")).toBeInTheDocument();
    await start();
    expectStopped(next, 0);
    expect(video(view).srcObject).toBe(next.stream);
  });

  it.each([false, true])("ignores late playback after unmount (failure=%s)", async (fails) => {
    const play = deferred<void>();
    const fake = fakeStream();
    acquire.mockResolvedValue(fake.stream);
    vi.mocked(HTMLMediaElement.prototype.play).mockReturnValue(play.promise);
    const view = render(<DocCapture {...props} />);
    await start();
    view.unmount();
    expectStopped(fake);
    await settle(play, undefined, fails);
    expectStopped(fake);
    expect(createPreview).not.toHaveBeenCalled();
    expect(onCapture).not.toHaveBeenCalled();
  });

  it.each([false, true])(
    "cannot stop a newer stream after stale playback (failure=%s)",
    async (fails) => {
      const oldPlay = deferred<void>();
      const old = fakeStream();
      const current = fakeStream();
      acquire.mockResolvedValueOnce(old.stream).mockResolvedValueOnce(current.stream);
      vi.mocked(HTMLMediaElement.prototype.play).mockReturnValueOnce(oldPlay.promise);
      const view = render(<DocCapture {...props} />);
      await start();
      await start();
      expectStopped(old);
      expectStopped(current, 0);
      await settle(oldPlay, undefined, fails);
      expectStopped(old);
      expectStopped(current, 0);
      expect(video(view).srcObject).toBe(current.stream);
      expect(video(view)).toHaveAttribute("aria-hidden", "false");
      expect(
        screen.queryByText("Could not access camera. Check permissions."),
      ).not.toBeInTheDocument();
      view.unmount();
      expectStopped(current);
    },
  );
});

describe("delayed canvas results", () => {
  it("drops an encoded photo after unmount", async () => {
    const fake = fakeStream();
    acquire.mockResolvedValue(fake.stream);
    const view = render(<DocCapture {...props} />);
    await start();
    takePhoto();
    view.unmount();
    expectStopped(fake);
    await encode();
    expectStopped(fake);
    expect(createPreview).not.toHaveBeenCalled();
    expect(onCapture).not.toHaveBeenCalled();
  });

  it("does not attach an old photo or stop a new account's stream", async () => {
    const a = fakeStream();
    const b = fakeStream();
    acquire.mockResolvedValueOnce(a.stream).mockResolvedValueOnce(b.stream);
    const view = render(<DocCapture key="A" {...props} />);
    await start();
    takePhoto();
    view.rerender(<DocCapture key="B" {...props} />);
    await start();
    await encode();
    expectStopped(a);
    expectStopped(b, 0);
    expect(video(view).srcObject).toBe(b.stream);
    expect(createPreview).not.toHaveBeenCalled();
    expect(onCapture).not.toHaveBeenCalled();
    view.unmount();
    expectStopped(b);
  });

  it("rejects a second old canvas callback after retake without stopping the new stream", async () => {
    const old = fakeStream();
    const current = fakeStream();
    acquire.mockResolvedValueOnce(old.stream).mockResolvedValueOnce(current.stream);
    const view = render(<DocCapture {...props} />);
    await start();
    takePhoto();
    takePhoto();
    await encode(0);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Retake" }));
    });
    expectStopped(old);
    expectStopped(current, 0);
    await encode(1);
    expectStopped(current, 0);
    expect(video(view).srcObject).toBe(current.stream);
    expect(createPreview).toHaveBeenCalledTimes(1);
    expect(screen.queryByAltText("")).not.toBeInTheDocument();
    expect(onCapture).not.toHaveBeenCalled();
    view.unmount();
    expectStopped(current);
  });

  it("keeps capture available after an empty canvas result", async () => {
    const fake = fakeStream();
    acquire.mockResolvedValue(fake.stream);
    render(<DocCapture {...props} />);
    await start();
    takePhoto();
    await encode(0, null);
    expectStopped(fake, 0);
    expect(createPreview).not.toHaveBeenCalled();
    takePhoto();
    await encode(1);
    expectStopped(fake);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it("ignores a repeated callback for an already-consumed canvas generation", async () => {
    const fake = fakeStream();
    acquire.mockResolvedValue(fake.stream);
    render(<DocCapture {...props} />);
    await start();
    takePhoto();
    await encode(0);
    await encode(0);
    expectStopped(fake);
    expect(createPreview).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it("retains generation protection with StrictMode effect replay", async () => {
    const pending = deferred<MediaStream>();
    const fake = fakeStream();
    acquire.mockReturnValue(pending.promise);
    const view = render(
      <StrictMode>
        <DocCapture {...props} />
      </StrictMode>,
    );
    await start();
    view.unmount();
    await settle(pending, fake.stream);
    expectStopped(fake);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(onCapture).not.toHaveBeenCalled();
  });
});
