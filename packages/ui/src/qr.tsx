import qrcode from "qrcode-generator";

export type QrErrorCorrection = "L" | "M" | "Q" | "H";

/**
 * Dark-module matrix for `value` (row-major, `matrix[row][col]`). Exported so
 * tests can rasterise + decode it, and so callers can render it however they
 * like. `typeNumber` 0 auto-fits the smallest version that holds the data.
 */
export function qrMatrix(value: string, level: QrErrorCorrection = "M"): boolean[][] {
  const model = qrcode(0, level);
  model.addData(value);
  model.make();
  const count = model.getModuleCount();
  const rows: boolean[][] = [];
  for (let row = 0; row < count; row += 1) {
    const cols: boolean[] = [];
    for (let col = 0; col < count; col += 1) {
      cols.push(model.isDark(row, col));
    }
    rows.push(cols);
  }
  return rows;
}

/** One SVG `<path>` `d` covering every dark module, offset by the quiet zone. */
function matrixToPath(matrix: boolean[][], quiet: number): string {
  let d = "";
  for (let row = 0; row < matrix.length; row += 1) {
    const cols = matrix[row] ?? [];
    for (let col = 0; col < cols.length; col += 1) {
      if (cols[col]) {
        d += `M${col + quiet} ${row + quiet}h1v1h-1z`;
      }
    }
  }
  return d;
}

export type QrCodeProps = {
  /** Data to encode (e.g. the rotating ticket payload). */
  value: string;
  /** Accessible name — the component renders as a single `role="img"`. */
  title: string;
  level?: QrErrorCorrection;
  /** Rendered square size in px. */
  size?: number;
  /** Quiet-zone width in modules; the QR spec minimum is 4. */
  quiet?: number;
  className?: string;
};

/**
 * A scannable QR matrix rendered as inline SVG. Deliberately hard-codes true
 * black-on-white (not theme tokens): scanners need maximum luminance contrast,
 * and a cream/charcoal QR fails to read. Renders server-side, so the encoder
 * never ships to the browser.
 */
export function QrCode({
  value,
  title,
  level = "M",
  size = 220,
  quiet = 4,
  className,
}: QrCodeProps) {
  const matrix = qrMatrix(value, level);
  const dimension = matrix.length + quiet * 2;
  const path = matrixToPath(matrix, quiet);

  return (
    <svg
      role="img"
      aria-label={title}
      viewBox={`0 0 ${dimension} ${dimension}`}
      width={size}
      height={size}
      shapeRendering="crispEdges"
      className={className}
    >
      <rect width={dimension} height={dimension} fill="#ffffff" />
      <path d={path} fill="#000000" />
    </svg>
  );
}
