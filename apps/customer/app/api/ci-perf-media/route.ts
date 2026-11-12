import { handleCiPerfMedia } from "../../../lib/ci-perf-media";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const GET = (request: Request) => handleCiPerfMedia(request);
export const POST = GET;
export const PUT = GET;
export const PATCH = GET;
export const DELETE = GET;
export const OPTIONS = GET;
export const HEAD = GET;
