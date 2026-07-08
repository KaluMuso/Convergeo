/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview; gated off in production */
"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { ImageGallery } from "@vergeo/ui/src/media/image-gallery";
import { UploadDropzone } from "@vergeo/ui/src/media/upload-dropzone";
import { useState } from "react";

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <h3 className="font-display text-lg text-display-ink">{title}</h3>
      {children}
    </div>
  );
}

const GALLERY_IMAGES = [
  { publicId: "vergeo5-preview/sample-1", alt: "Sample product front" },
  { publicId: "vergeo5-preview/sample-2", alt: "Sample product side" },
  { publicId: "vergeo5-preview/sample-3", alt: "Sample product detail" },
];

export function MediaSection() {
  const [files, setFiles] = useState<File[]>([]);

  return (
    <section id="media" className="scroll-mt-4 flex flex-col gap-6">
      <h2 className="font-display text-2xl text-display-ink">Media</h2>

      <SectionBlock title="Cloudinary image (placeholder publicId)">
        <div className="max-w-xs">
          <CloudinaryImage
            publicId="vergeo5-preview/placeholder-404"
            alt="Placeholder demo image"
            ratio="4/3"
            cloudName="demo"
          />
        </div>
      </SectionBlock>

      <SectionBlock title="Image gallery">
        <ImageGallery
          images={GALLERY_IMAGES}
          cloudName="demo"
          ratio="4/3"
          indicatorLabel={(current, total) => `${current} / ${total}`}
          previousLabel="Previous image"
          nextLabel="Next image"
        />
      </SectionBlock>

      <SectionBlock title="Upload dropzone">
        <UploadDropzone
          files={files}
          onFilesChange={setFiles}
          dropLabel="Drop images here"
          browseLabel="Browse files"
          moveUpLabel="Move up"
          moveDownLabel="Move down"
          removeLabel="Remove"
          compressHint={
            <span className="text-sm text-text-2">Images are compressed before upload.</span>
          }
          onReject={(count) => console.warn(`Rejected ${count} files (max 8)`)}
        />
      </SectionBlock>
    </section>
  );
}
