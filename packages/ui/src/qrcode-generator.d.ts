/**
 * Minimal ambient types for `qrcode-generator` (ships no bundled types).
 * Only the surface we use is declared; keeps us off a separate @types dep.
 */
declare module "qrcode-generator" {
  type QrErrorCorrectionLevel = "L" | "M" | "Q" | "H";

  interface QrCodeModel {
    addData(data: string): void;
    make(): void;
    getModuleCount(): number;
    isDark(row: number, col: number): boolean;
  }

  /** `typeNumber` 0 = auto-fit the smallest version that holds the data. */
  function qrcode(typeNumber: number, errorCorrectionLevel: QrErrorCorrectionLevel): QrCodeModel;

  export = qrcode;
}
