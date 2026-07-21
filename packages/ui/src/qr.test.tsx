// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render } from "@testing-library/react";
import jsQR from "jsqr";
import { afterEach, describe, expect, it } from "vitest";

import { QrCode, qrMatrix } from "./qr";

afterEach(cleanup);

/** Rasterise a module matrix to an RGBA buffer a real decoder can read. */
function rasterise(matrix: boolean[][], scale: number, quiet: number) {
  const modules = matrix.length;
  const dim = (modules + quiet * 2) * scale;
  const data = new Uint8ClampedArray(dim * dim * 4).fill(255); // opaque white
  for (let row = 0; row < modules; row += 1) {
    for (let col = 0; col < modules; col += 1) {
      if (!matrix[row]?.[col]) continue;
      for (let dy = 0; dy < scale; dy += 1) {
        for (let dx = 0; dx < scale; dx += 1) {
          const x = (col + quiet) * scale + dx;
          const y = (row + quiet) * scale + dy;
          const index = (y * dim + x) * 4;
          data[index] = 0;
          data[index + 1] = 0;
          data[index + 2] = 0;
          data[index + 3] = 255;
        }
      }
    }
  }
  return { data, dim };
}

describe("qrMatrix", () => {
  it("round-trips a rotating ticket payload through a real QR decoder", () => {
    const payload = "a1b2c3d4-e5f6-7890-abcd-ef1234567890:29045678:0a1b2c3d4e5f6a7b";
    const matrix = qrMatrix(payload, "M");

    expect(matrix.length).toBeGreaterThan(20);
    expect(matrix.every((row) => row.length === matrix.length)).toBe(true);

    const { data, dim } = rasterise(matrix, 6, 4);
    const decoded = jsQR(data, dim, dim);
    expect(decoded?.data).toBe(payload);
  });
});

describe("QrCode", () => {
  it("renders one accessible SVG sized to the module count plus quiet zone", () => {
    const { getByRole } = render(<QrCode value="VERGEO-TICKET" title="Ticket QR" quiet={4} />);
    const svg = getByRole("img", { name: "Ticket QR" });
    const modules = qrMatrix("VERGEO-TICKET").length;
    expect(svg.getAttribute("viewBox")).toBe(`0 0 ${modules + 8} ${modules + 8}`);
  });
});
