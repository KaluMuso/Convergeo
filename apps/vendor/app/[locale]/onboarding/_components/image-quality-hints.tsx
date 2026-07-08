type ImageQualityHintsProps = {
  heading: string;
  light: string;
  steady: string;
  frame: string;
  face: string;
};

export function ImageQualityHints({ heading, light, steady, frame, face }: ImageQualityHintsProps) {
  return (
    <aside
      aria-label={heading}
      className="rounded border border-border bg-bg-2 p-3 text-sm text-text-2"
    >
      <p className="mb-2 font-medium text-text">{heading}</p>
      <ul className="m-0 list-disc space-y-1 ps-4">
        <li>{light}</li>
        <li>{steady}</li>
        <li>{frame}</li>
        <li>{face}</li>
      </ul>
    </aside>
  );
}
