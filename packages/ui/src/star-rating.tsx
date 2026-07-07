import type { KeyboardEvent, ReactNode } from "react";
import { useId } from "react";

type StarRatingBaseProps = {
  className?: string;
  starLabel?: string;
};

export type StarRatingDisplayProps = StarRatingBaseProps & {
  mode?: "display";
  value: number;
  reviewCount?: number;
  /** Rendered when reviewCount is 0 — not zero stars */
  noReviewsSlot?: ReactNode;
  reviewCountLabel?: string;
};

export type StarRatingInputProps = StarRatingBaseProps & {
  mode: "input";
  value: number;
  onChange: (value: number) => void;
  name: string;
  inputAriaLabel: string;
};

export type StarRatingProps = StarRatingDisplayProps | StarRatingInputProps;

const STAR_COUNT = 5;

function clampRating(value: number): number {
  return Math.min(STAR_COUNT, Math.max(0, value));
}

function StarIcon({ fill, clipId }: { fill: "empty" | "half" | "full"; clipId: string }) {
  const starPath =
    "M12 2l2.9 6.26L22 9.27l-5 4.87L18.2 22 12 18.56 5.8 22 7 14.14l-5-4.87 7.1-1.01L12 2z";

  if (fill === "full") {
    return (
      <svg
        width={16}
        height={16}
        viewBox="0 0 24 24"
        aria-hidden
        data-star-fill="full"
        style={{ flexShrink: 0 }}
      >
        <path d={starPath} fill="var(--accent)" />
      </svg>
    );
  }

  if (fill === "half") {
    return (
      <svg
        width={16}
        height={16}
        viewBox="0 0 24 24"
        aria-hidden
        data-star-fill="half"
        style={{ flexShrink: 0 }}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x="0" y="0" width="12" height="24" />
          </clipPath>
        </defs>
        <path d={starPath} fill="none" stroke="var(--text-3)" strokeWidth={1.5} />
        <path d={starPath} fill="var(--accent)" clipPath={`url(#${clipId})`} />
      </svg>
    );
  }

  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      aria-hidden
      data-star-fill="empty"
      style={{ flexShrink: 0 }}
    >
      <path d={starPath} fill="none" stroke="var(--text-3)" strokeWidth={1.5} />
    </svg>
  );
}

function getStarFill(index: number, value: number): "empty" | "half" | "full" {
  const starValue = index + 1;
  if (value >= starValue) return "full";
  if (value >= starValue - 0.5) return "half";
  return "empty";
}

function StarRow({ value }: { value: number }) {
  const clipId = useId();
  const clamped = clampRating(value);

  return (
    <span
      role="img"
      aria-hidden
      data-testid="star-rating-stars"
      style={{ display: "inline-flex", gap: 2, alignItems: "center" }}
    >
      {Array.from({ length: STAR_COUNT }, (_, index) => (
        <StarIcon key={index} fill={getStarFill(index, clamped)} clipId={`${clipId}-${index}`} />
      ))}
    </span>
  );
}

function StarRatingInput({
  value,
  onChange,
  name,
  inputAriaLabel,
  className,
}: StarRatingInputProps) {
  const clipId = useId();
  const clamped = clampRating(value);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      event.preventDefault();
      onChange(Math.min(STAR_COUNT, clamped + 1));
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      event.preventDefault();
      onChange(Math.max(1, clamped - 1));
    }
  };

  return (
    <div
      className={className}
      role="radiogroup"
      aria-label={inputAriaLabel}
      data-testid="star-rating-input"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      style={{ display: "inline-flex", gap: 4 }}
    >
      {Array.from({ length: STAR_COUNT }, (_, index) => {
        const starValue = index + 1;
        const checked = clamped === starValue;

        return (
          <label
            key={starValue}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              minWidth: 44,
              minHeight: 44,
              cursor: "pointer",
            }}
          >
            <input
              type="radio"
              name={name}
              value={starValue}
              checked={checked}
              onChange={() => onChange(starValue)}
              style={{
                position: "absolute",
                opacity: 0,
                width: 1,
                height: 1,
                overflow: "hidden",
              }}
            />
            <StarIcon fill={checked ? "full" : "empty"} clipId={`${clipId}-${starValue}`} />
          </label>
        );
      })}
    </div>
  );
}

export function StarRating(props: StarRatingProps) {
  if (props.mode === "input") {
    return <StarRatingInput {...props} />;
  }

  const { value, reviewCount, noReviewsSlot, reviewCountLabel, className } = props;

  if (reviewCount !== undefined && reviewCount === 0) {
    return (
      <div className={className} data-testid="star-rating-no-reviews">
        {noReviewsSlot}
      </div>
    );
  }

  return (
    <div
      className={className}
      data-testid="star-rating-display"
      style={{ display: "inline-flex", alignItems: "center", gap: "var(--sp-2)" }}
    >
      <StarRow value={value} />
      {reviewCountLabel ? (
        <span style={{ fontSize: "var(--fs-sm)", color: "var(--text-2)" }}>{reviewCountLabel}</span>
      ) : null}
    </div>
  );
}
