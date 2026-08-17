export type OpenGraphSearchParams = {
  name?: string;
  price?: string;
};

export function resolveOpenGraphParams(searchParams: OpenGraphSearchParams | null | undefined): {
  displayName: string;
  displayPrice: string | null;
} {
  const params = searchParams ?? {};
  const displayName = params.name?.trim() || "Convergeo";
  const displayPrice = params.price?.trim() || null;
  return { displayName, displayPrice };
}
