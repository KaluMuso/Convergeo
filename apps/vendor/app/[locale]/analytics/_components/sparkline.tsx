/**
 * Inline-SVG sparkline — zero chart dependencies, a handful of bytes of markup.
 * Renders a normalized polyline with a dot on the latest point; theme-aware via
 * `currentColor`. Flat/empty series degrade gracefully to a baseline line.
 */
type SparklineProps = {
  values: number[];
  label: string;
};

const WIDTH = 132;
const HEIGHT = 36;
const PAD = 3;

export function Sparkline({ values, label }: SparklineProps) {
  const series = values.length > 0 ? values : [0];
  const max = Math.max(...series, 0);
  const min = Math.min(...series, 0);
  const range = max - min || 1;
  const innerW = WIDTH - PAD * 2;
  const innerH = HEIGHT - PAD * 2;
  const step = series.length > 1 ? innerW / (series.length - 1) : 0;

  const coords = series.map((value, index) => {
    const x = PAD + index * step;
    const y = PAD + innerH * (1 - (value - min) / range);
    return { x, y };
  });

  const points = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const last = coords[coords.length - 1];

  return (
    <svg
      aria-label={label}
      className="text-primary"
      height={HEIGHT}
      preserveAspectRatio="none"
      role="img"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width="100%"
    >
      <polyline
        fill="none"
        points={points}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
      />
      {last ? <circle cx={last.x} cy={last.y} fill="currentColor" r={2.4} /> : null}
    </svg>
  );
}
