type JsQrModule = typeof import("jsqr");

let jsQrModulePromise: Promise<JsQrModule> | null = null;

function loadJsQr(): Promise<JsQrModule> {
  if (!jsQrModulePromise) {
    jsQrModulePromise = import("jsqr");
  }
  return jsQrModulePromise;
}

export async function decodeQrFromImageData(imageData: ImageData): Promise<string | null> {
  const jsQR = (await loadJsQr()).default;
  const result = jsQR(imageData.data, imageData.width, imageData.height, {
    inversionAttempts: "dontInvert",
  });
  return result?.data ?? null;
}
