import { formatVariantLabel } from "../pdp/variant-selection";

type VariantLineLabelProps = {
  options: Array<{ group: string; value: string }> | null | undefined;
  /** Localized "{group}: {value}" template. */
  template: string;
  separator: string;
  testId?: string;
  className?: string;
};

/** The colour/size a buyer chose, e.g. "Colour: Red · Size: M". Renders nothing without options. */
export function VariantLineLabel({
  options,
  template,
  separator,
  testId,
  className = "block text-xs text-text-2",
}: VariantLineLabelProps) {
  if (!options || options.length === 0) {
    return null;
  }
  return (
    <span className={className} data-testid={testId}>
      {formatVariantLabel(options, template, separator)}
    </span>
  );
}
