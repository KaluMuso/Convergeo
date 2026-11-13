import { handleCiPerfProxy } from "../../../../lib/ci-perf-proxy";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const GET = (request: Request) => handleCiPerfProxy(request);
// Every method must also be unavailable outside the harness.
export const POST = GET;
export const PUT = GET;
export const PATCH = GET;
export const DELETE = GET;
export const OPTIONS = GET;
export const HEAD = GET;
