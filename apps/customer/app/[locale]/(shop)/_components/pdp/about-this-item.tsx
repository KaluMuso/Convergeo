"use client";

import { useState } from "react";

export type AboutThisItemProps = {
  paragraphs: string[];
  seeMoreLabel: string;
  seeLessLabel: string;
};

const LINE_CLAMP = 6;

export function AboutThisItem({ paragraphs, seeMoreLabel, seeLessLabel }: AboutThisItemProps) {
  const [expanded, setExpanded] = useState(false);
  if (paragraphs.length === 0) {
    return null;
  }

  const bulletMode = paragraphs.some((line) => line.trim().startsWith("-"));

  return (
    <section data-testid="pdp-about" className="flex flex-col gap-2">
      {bulletMode ? (
        <ul
          className={[
            "m-0 list-disc space-y-1 pl-5 text-sm leading-relaxed text-text-2",
            expanded ? "" : "line-clamp-[6]",
          ].join(" ")}
        >
          {paragraphs.map((line, index) => (
            <li key={index}>{line.replace(/^\s*-\s*/, "")}</li>
          ))}
        </ul>
      ) : (
        <div
          className={[
            "flex flex-col gap-2 text-sm leading-relaxed text-text-2",
            expanded ? "" : "line-clamp-[6]",
          ].join(" ")}
        >
          {paragraphs.map((paragraph, index) => (
            <p key={index} className="m-0">
              {paragraph}
            </p>
          ))}
        </div>
      )}
      {paragraphs.join("").length > LINE_CLAMP * 40 ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="w-fit text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {expanded ? seeLessLabel : seeMoreLabel}
        </button>
      ) : null}
    </section>
  );
}
