type LayoutProps = { children: React.ReactNode };

// Messages come from the parent listings layout (vendor.listings + vendor.plans).
export const dynamic = "force-dynamic";

export default function NewListingLayout({ children }: LayoutProps) {
  return children;
}
