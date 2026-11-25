import { eventCountdownState, type EventCountdownState } from "../_lib/countdown";
import { effectiveInstanceEndMs } from "../_lib/instance-time";

export type EventCountdownLabels = {
  ended: string;
  today: string;
  tomorrow: string;
  days: string;
};

type EventCountdownProps = {
  startsAt: string;
  endsAt: string | null;
  locale: string;
  labels: EventCountdownLabels;
};

function labelForState(state: EventCountdownState, labels: EventCountdownLabels): string {
  if (state.kind === "ended") {
    return labels.ended;
  }
  if (state.kind === "today") {
    return labels.today.replace("{time}", state.timeLabel);
  }
  if (state.kind === "tomorrow") {
    return labels.tomorrow;
  }
  return labels.days.replace("{count}", String(state.days));
}

export function EventCountdown({ startsAt, endsAt, locale, labels }: EventCountdownProps) {
  const endsAtMs = effectiveInstanceEndMs({
    starts_at: startsAt,
    ends_at: endsAt,
  });
  const state = eventCountdownState(startsAt, endsAtMs, new Date(), locale);
  if (!state) {
    return null;
  }

  return (
    <p data-testid="event-countdown" className="text-sm font-medium text-panel-muted">
      {labelForState(state, labels)}
    </p>
  );
}
