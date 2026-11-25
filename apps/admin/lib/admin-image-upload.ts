/** Client-only Cloudinary upload helpers for admin merchandising (listing folder). */

const MAX_UPLOAD_RETRIES = 3;

type SignUploadResponse = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
  max_file_size: number;
};

type CloudinaryUploadResponse = {
  public_id: string;
};

export async function downscaleImageFile(
  file: File,
  maxEdge = 1600,
  quality = 0.86,
): Promise<File> {
  const mimeType = "image/jpeg";
  if (!file.type.startsWith("image/") || file.size === 0) {
    return file;
  }
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) {
    return file;
  }
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    return file;
  }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, mimeType, quality);
  });
  if (!blob) {
    return file;
  }
  const baseName = file.name.replace(/\.[^.]+$/, "") || "merch-image";
  return new File([blob], `${baseName}.jpg`, { type: mimeType, lastModified: Date.now() });
}

async function uploadToCloudinary(
  file: Blob,
  signed: SignUploadResponse,
): Promise<CloudinaryUploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `https://api.cloudinary.com/v1_1/${signed.cloud_name}/image/upload`);
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error("Cloudinary upload failed"));
        return;
      }
      try {
        const payload = JSON.parse(xhr.responseText) as CloudinaryUploadResponse;
        if (!payload.public_id) {
          reject(new Error("Cloudinary response missing public_id"));
          return;
        }
        resolve(payload);
      } catch {
        reject(new Error("Invalid Cloudinary response"));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during Cloudinary upload"));
    const formData = new FormData();
    formData.append("file", file);
    formData.append("api_key", signed.api_key);
    formData.append("timestamp", String(signed.timestamp));
    formData.append("signature", signed.signature);
    formData.append("folder", signed.folder);
    formData.append("allowed_formats", signed.allowed_formats);
    formData.append("max_file_size", String(signed.max_file_size));
    xhr.send(formData);
  });
}

export async function uploadSignedImage(
  file: Blob,
  signed: SignUploadResponse,
): Promise<CloudinaryUploadResponse> {
  let lastError: Error | null = null;
  for (let attempt = 1; attempt <= MAX_UPLOAD_RETRIES; attempt += 1) {
    try {
      return await uploadToCloudinary(file, signed);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Upload failed");
    }
  }
  throw lastError ?? new Error("Upload failed");
}
