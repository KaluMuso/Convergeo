"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";

const MAX_FILES = 8;

export type UploadDropzoneProps = {
  files: File[];
  onFilesChange: (files: File[]) => void;
  onReject?: (attemptedCount: number) => void;
  fileProgress?: number[];
  dropLabel: string;
  browseLabel: string;
  moveUpLabel: string;
  moveDownLabel: string;
  removeLabel: string;
  compressHint?: ReactNode;
  accept?: string;
  className?: string;
};

function fileKey(file: File, index: number): string {
  return `${file.name}-${file.size}-${file.lastModified}-${index}`;
}

export function UploadDropzone({
  files,
  onFilesChange,
  onReject,
  fileProgress = [],
  dropLabel,
  browseLabel,
  moveUpLabel,
  moveDownLabel,
  removeLabel,
  compressHint,
  accept = "image/*",
  className,
}: UploadDropzoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);

  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviewUrls(urls);
    return () => {
      for (const url of urls) {
        URL.revokeObjectURL(url);
      }
    };
  }, [files]);

  const addFiles = useCallback(
    (incoming: File[]) => {
      if (incoming.length === 0) {
        return;
      }
      const combined = [...files, ...incoming];
      if (combined.length > MAX_FILES) {
        onReject?.(combined.length);
        return;
      }
      onFilesChange(combined);
    },
    [files, onFilesChange, onReject],
  );

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const selected = event.target.files ? Array.from(event.target.files) : [];
      addFiles(selected);
      event.target.value = "";
    },
    [addFiles],
  );

  const handleDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragOver(false);
      const dropped = Array.from(event.dataTransfer.files);
      addFiles(dropped);
    },
    [addFiles],
  );

  const removeAt = useCallback(
    (index: number) => {
      onFilesChange(files.filter((_, i) => i !== index));
    },
    [files, onFilesChange],
  );

  const move = useCallback(
    (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target < 0 || target >= files.length) {
        return;
      }
      const next = [...files];
      const current = next[index];
      const swap = next[target];
      if (!current || !swap) {
        return;
      }
      next[index] = swap;
      next[target] = current;
      onFilesChange(next);
    },
    [files, onFilesChange],
  );

  return (
    <div className={className} style={{ display: "grid", gap: "var(--sp-4)" }}>
      <div
        data-testid="upload-dropzone"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          border: dragOver ? "2px dashed var(--primary)" : "2px dashed var(--border)",
          borderRadius: "var(--r)",
          padding: "var(--sp-6)",
          textAlign: "center",
          background: dragOver ? "var(--primary-tint)" : "var(--surface)",
          display: "grid",
          gap: "var(--sp-3)",
        }}
      >
        <p>{dropLabel}</p>
        <label htmlFor={inputId}>
          <input
            ref={inputRef}
            id={inputId}
            data-testid="upload-input"
            type="file"
            accept={accept}
            multiple
            onChange={handleInputChange}
            style={{ display: "none" }}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            style={{ minHeight: "44px", minWidth: "44px" }}
          >
            {browseLabel}
          </button>
        </label>
        {compressHint ? <div data-testid="compress-hint">{compressHint}</div> : null}
      </div>

      {files.length > 0 ? (
        <ul
          data-testid="upload-file-list"
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "grid",
            gap: "var(--sp-3)",
          }}
        >
          {files.map((file, index) => {
            const progress = fileProgress[index] ?? 0;
            const preview = previewUrls[index];
            return (
              <li
                key={fileKey(file, index)}
                data-testid={`upload-file-${index}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto",
                  gap: "var(--sp-3)",
                  alignItems: "center",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r)",
                  padding: "var(--sp-3)",
                }}
              >
                {preview ? (
                  <img
                    src={preview}
                    alt=""
                    data-testid={`upload-preview-${index}`}
                    style={{
                      width: "64px",
                      height: "64px",
                      objectFit: "cover",
                      borderRadius: "var(--r-sm)",
                    }}
                  />
                ) : null}
                <div style={{ display: "grid", gap: "var(--sp-2)" }}>
                  <span>{file.name}</span>
                  <div
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={progress}
                    data-testid={`upload-progress-${index}`}
                    style={{
                      height: "6px",
                      borderRadius: "var(--r-pill)",
                      background: "var(--bg-2)",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width: `${Math.min(100, Math.max(0, progress))}%`,
                        height: "100%",
                        background: "var(--primary)",
                        transition: "width var(--dur-fast) var(--ease-std)",
                      }}
                    />
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-1)" }}>
                  <button
                    type="button"
                    aria-label={moveUpLabel}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                    data-testid={`upload-move-up-${index}`}
                    style={{ minHeight: "44px", minWidth: "44px" }}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={moveDownLabel}
                    disabled={index === files.length - 1}
                    onClick={() => move(index, 1)}
                    data-testid={`upload-move-down-${index}`}
                    style={{ minHeight: "44px", minWidth: "44px" }}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    aria-label={removeLabel}
                    onClick={() => removeAt(index)}
                    data-testid={`upload-remove-${index}`}
                    style={{ minHeight: "44px", minWidth: "44px" }}
                  >
                    ×
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
