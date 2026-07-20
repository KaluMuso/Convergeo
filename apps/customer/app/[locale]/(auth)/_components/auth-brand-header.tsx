type AuthBrandHeaderProps = {
  appName: string;
  tagline: string;
};

/**
 * Hero-level brand band for auth routes (audit E18). Server Component — no client
 * boundary. Mirrors home hero token usage (panel plane, display wordmark) at
 * auth-appropriate height for 360px-first viewports.
 */
export function AuthBrandHeader({ appName, tagline }: AuthBrandHeaderProps) {
  return (
    <header
      data-testid="auth-brand-header"
      className="relative left-1/2 right-1/2 -ml-[50vw] -mr-[50vw] w-screen overflow-hidden bg-panel text-panel-text"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-90"
        style={{
          background:
            "radial-gradient(120% 80% at 85% 20%, color-mix(in srgb, var(--primary) 35%, transparent) 0%, transparent 55%), linear-gradient(135deg, var(--panel) 0%, color-mix(in srgb, var(--primary-deep) 55%, var(--panel)) 100%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-6 top-4 h-36 w-36 rounded-full bg-primary/20 blur-2xl motion-reduce:blur-none sm:h-48 sm:w-48"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 left-[10%] h-28 w-28 rounded-full bg-accent/15 blur-xl motion-reduce:blur-none"
      />

      <div className="relative mx-auto flex w-full max-w-lg flex-col items-center gap-2 px-4 py-10 text-center sm:py-12">
        <p
          data-testid="auth-brand-wordmark"
          className="font-display text-hero leading-none tracking-tight text-panel-text"
        >
          {appName}
        </p>
        <p className="max-w-xs font-body text-body text-panel-muted">{tagline}</p>
      </div>
    </header>
  );
}
