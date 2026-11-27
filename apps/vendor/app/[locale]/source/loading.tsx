import { VendorPageSkeleton } from "../_components/page-skeleton";
import { VendorPage } from "../_components/vendor-page";

export default function Loading() {
  return (
    <VendorPage width="full">
      <VendorPageSkeleton rows={4} />
    </VendorPage>
  );
}
