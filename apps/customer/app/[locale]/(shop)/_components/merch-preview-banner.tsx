type MerchPreviewBannerProps = {
  message: string;
};

/** Shown on customer home when `?merch_preview=` draft overlay is active. */
export function MerchPreviewBanner({ message }: MerchPreviewBannerProps) {
  return (
    <div
      role="status"
      data-testid="merch-preview-banner"
      className="rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-text"
    >
      {message}
    </div>
  );
}
