import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import { CanonicalSubmissionDetails } from "./PendingCanonicalQueue";

it("shows submitted text and structured specifications as escaped review content", () => {
  const markup = renderToStaticMarkup(
    <CanonicalSubmissionDetails
      heading="Product details"
      item={{
        brand: "Supplier brand",
        description: "<script>untrusted</script>\nInstructions",
        spec: { weight: { value: 2, unit: "kg" } },
      }}
    />,
  );
  expect(markup).toContain('aria-label="Product details"');
  expect(markup).toContain("Supplier brand");
  expect(markup).toContain("&lt;script&gt;untrusted&lt;/script&gt;");
  expect(markup).not.toContain("<script>");
  expect(markup).toContain("&quot;weight&quot;");
  expect(markup).toContain("&quot;kg&quot;");
});
