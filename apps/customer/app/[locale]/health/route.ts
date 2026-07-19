function buildId(): string {
  return (
    process.env.NEXT_PUBLIC_VERGEO_BUILD_ID ||
    process.env.VERCEL_GIT_COMMIT_SHA ||
    process.env.GIT_SHA ||
    "unknown"
  );
}

export function GET() {
  return Response.json({
    status: "ok",
    app: "customer",
    env: process.env.NEXT_PUBLIC_VERGEO_ENV || process.env.VERCEL_ENV || "unknown",
    buildId: buildId(),
  });
}
