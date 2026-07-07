// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UploadDropzone } from "./upload-dropzone";

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock-preview");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const labels = {
  dropLabel: "Drop images here",
  browseLabel: "Browse files",
  moveUpLabel: "Move up",
  moveDownLabel: "Move down",
  removeLabel: "Remove file",
};

function makeFile(name: string): File {
  return new File(["pixels"], name, { type: "image/jpeg" });
}

function Harness({
  initial = [] as File[],
  onReject,
}: {
  initial?: File[];
  onReject?: (count: number) => void;
}) {
  const [files, setFiles] = useState(initial);
  return <UploadDropzone files={files} onFilesChange={setFiles} onReject={onReject} {...labels} />;
}

describe("UploadDropzone", () => {
  it("rejects more than 8 files via callback", async () => {
    const user = userEvent.setup();
    const onReject = vi.fn();
    const eight = Array.from({ length: 8 }, (_, i) => makeFile(`img-${i}.jpg`));

    render(<Harness initial={eight} onReject={onReject} />);

    const input = screen.getByTestId("upload-input");
    const ninth = makeFile("img-9.jpg");
    await user.upload(input, ninth);

    expect(onReject).toHaveBeenCalledWith(9);
    expect(screen.getByTestId("upload-file-list").children).toHaveLength(8);
  });

  it("reorders files with move buttons", async () => {
    const user = userEvent.setup();
    const files = [makeFile("a.jpg"), makeFile("b.jpg")];

    render(<Harness initial={files} />);

    expect(screen.getByTestId("upload-file-0")).toHaveTextContent("a.jpg");
    expect(screen.getByTestId("upload-file-1")).toHaveTextContent("b.jpg");

    await user.click(screen.getByTestId("upload-move-down-0"));

    expect(screen.getByTestId("upload-file-0")).toHaveTextContent("b.jpg");
    expect(screen.getByTestId("upload-file-1")).toHaveTextContent("a.jpg");
  });

  it("revokes object URLs on unmount", () => {
    const files = [makeFile("preview.jpg")];

    const { unmount } = render(<Harness initial={files} />);
    expect(screen.getByTestId("upload-preview-0")).toBeInTheDocument();

    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });
});
