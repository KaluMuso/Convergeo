/* eslint-disable @vergeo/no-hardcoded-strings -- dev-only UI preview; gated off in production */
import { CardsSection } from "./_sections/cards";
import { FormsSection } from "./_sections/forms";
import { MediaSection } from "./_sections/media";
import { NavSection } from "./_sections/nav";
import { OverlaysSection } from "./_sections/overlays";
import { StatesSection } from "./_sections/states";

const SECTIONS = [
  { id: "forms", label: "Form controls" },
  { id: "cards", label: "Cards & prices" },
  { id: "overlays", label: "Overlays" },
  { id: "states", label: "Feedback states" },
  { id: "nav", label: "Navigation" },
  { id: "media", label: "Media" },
] as const;

export default function UiPreviewPage() {
  return (
    <main id="ui-preview-main" className="mx-auto flex max-w-3xl flex-col gap-10 px-4 py-6">
      <header className="flex flex-col gap-2 border-b border-border pb-6">
        <p className="text-sm font-medium uppercase tracking-wide text-text-3">Dev only</p>
        <h1 className="font-display text-3xl text-display-ink">Vergeo5 UI Kit Preview</h1>
        <p className="text-text-2">
          Gallery of every component in <code className="text-sm">@vergeo/ui</code> — not shipped in
          production builds.
        </p>
        <nav aria-label="Section index" className="mt-2">
          <ul className="flex flex-wrap gap-2">
            {SECTIONS.map((section) => (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  className="inline-flex min-h-11 items-center rounded-pill border border-border bg-surface px-3 text-sm font-medium text-primary hover:bg-primary-tint focus-visible:outline-none focus-visible:shadow-focusRing"
                >
                  {section.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <FormsSection />
      <CardsSection />
      <OverlaysSection />
      <StatesSection />
      <NavSection />
      <MediaSection />
    </main>
  );
}
