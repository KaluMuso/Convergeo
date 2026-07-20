export function canAcceptQuote(jobStatus: string | null | undefined, quoteStatus: string): boolean {
  return (jobStatus === "open" || jobStatus === "quoted") && quoteStatus === "submitted";
}

export function shouldShowCompletion(
  jobStatus: string | null | undefined,
  quoteStatus: string | null | undefined,
): boolean {
  return quoteStatus === "accepted" && jobStatus !== "completed" && jobStatus !== "cancelled";
}
