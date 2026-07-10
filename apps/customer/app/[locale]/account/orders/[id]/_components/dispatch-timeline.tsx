import type { TimelineStep } from "../../_components/orders-api";

/** Parsed from M13-P06 admin dispatch notes: `[dispatch] courier=X | tracking: Y`. */
const DISPATCH_NOTE_RE = /^\[dispatch\]\s*courier=(.+?)\s*\|\s*tracking:\s*(.+)$/i;

export type DispatchOrderEvent = {
  note: string | null;
  toStatus: string | null;
  occurredAt: string | null;
};

export type DispatchStatusUpdate = {
  statusKey: string;
  label: string;
  occurredAt: string | null;
  detail?: string | null;
};

export type DispatchTimelineLabels = {
  title: string;
  courier: string;
  tracking: string;
  empty: string;
  statusUpdates: string;
};

export type DispatchTimelineProps = {
  fulfilment: string;
  status: string;
  courier?: string | null;
  trackingNote?: string | null;
  statusUpdates: DispatchStatusUpdate[];
  labels: DispatchTimelineLabels;
};

const DISPATCH_STEP_KEYS = new Set(["shipped", "delivered", "processing"]);

const TIMELINE_LABEL_KEY: Record<string, string> = {
  processing: "processing",
  shipped: "shipped",
  delivered: "delivered",
};

export function parseDispatchNote(
  note: string | null | undefined,
): { courier: string; trackingNote: string } | null {
  if (!note) {
    return null;
  }
  const match = DISPATCH_NOTE_RE.exec(note.trim());
  if (!match) {
    return null;
  }
  const courier = match[1]?.trim();
  const trackingNote = match[2]?.trim();
  if (!courier || !trackingNote) {
    return null;
  }
  return { courier, trackingNote };
}

/** Extract latest admin dispatch courier + tracking from order_events-shaped rows. */
export function extractDispatchFromEvents(events: readonly DispatchOrderEvent[]): {
  courier: string | null;
  trackingNote: string | null;
} {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const parsed = parseDispatchNote(events[index]?.note);
    if (parsed) {
      return parsed;
    }
  }
  return { courier: null, trackingNote: null };
}

export function buildDispatchStatusUpdates(
  timeline: readonly TimelineStep[],
  stepLabels: Record<string, string>,
  events: readonly DispatchOrderEvent[] = [],
): DispatchStatusUpdate[] {
  const updates: DispatchStatusUpdate[] = [];

  for (const step of timeline) {
    if (!DISPATCH_STEP_KEYS.has(step.step_key)) {
      continue;
    }
    if (step.state === "upcoming" || step.state === "skipped") {
      continue;
    }
    const labelKey = TIMELINE_LABEL_KEY[step.step_key];
    updates.push({
      statusKey: step.step_key,
      label: (labelKey && stepLabels[labelKey]) || step.step_key,
      occurredAt: step.occurred_at,
    });
  }

  for (const event of events) {
    const parsed = parseDispatchNote(event.note);
    if (!parsed || !event.occurredAt) {
      continue;
    }
    updates.push({
      statusKey: `dispatch-${event.toStatus ?? "update"}`,
      label: parsed.courier,
      occurredAt: event.occurredAt,
      detail: parsed.trackingNote,
    });
  }

  updates.sort((left, right) => {
    if (!left.occurredAt) {
      return 1;
    }
    if (!right.occurredAt) {
      return -1;
    }
    return new Date(left.occurredAt).getTime() - new Date(right.occurredAt).getTime();
  });

  return updates;
}

function shouldShowDispatchTimeline(fulfilment: string, status: string): boolean {
  if (fulfilment !== "delivery") {
    return false;
  }
  return ["processing", "shipped", "delivered", "completed"].includes(status);
}

export function DispatchTimeline({
  fulfilment,
  status,
  courier,
  trackingNote,
  statusUpdates,
  labels,
}: DispatchTimelineProps) {
  if (!shouldShowDispatchTimeline(fulfilment, status)) {
    return null;
  }

  const hasCourier = Boolean(courier?.trim());
  const hasTracking = Boolean(trackingNote?.trim());
  const hasUpdates = statusUpdates.length > 0;

  if (!hasCourier && !hasTracking && !hasUpdates) {
    return null;
  }

  return (
    <section
      aria-labelledby="dispatch-timeline-heading"
      className="space-y-3 rounded border border-border bg-surface p-4"
    >
      <h3 id="dispatch-timeline-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>

      {hasCourier ? (
        <dl className="space-y-1 text-sm">
          <div className="flex flex-wrap justify-between gap-2">
            <dt className="text-text-2">{labels.courier}</dt>
            <dd className="font-medium text-display-ink">{courier}</dd>
          </div>
        </dl>
      ) : null}

      {hasTracking ? (
        <dl className="space-y-1 text-sm">
          <div className="space-y-1">
            <dt className="text-text-2">{labels.tracking}</dt>
            <dd className="text-display-ink">{trackingNote}</dd>
          </div>
        </dl>
      ) : null}

      {hasUpdates ? (
        <div className="space-y-2">
          <p className="text-sm font-medium text-text-2">{labels.statusUpdates}</p>
          <ol className="space-y-2">
            {statusUpdates.map((update) => (
              <li
                key={`${update.statusKey}-${update.occurredAt ?? "pending"}`}
                className="rounded border border-border bg-bg-2 px-3 py-2 text-sm"
              >
                <p className="font-medium text-display-ink">{update.label}</p>
                {update.detail ? <p className="mt-1 text-text-2">{update.detail}</p> : null}
                {update.occurredAt ? (
                  <time
                    className="mt-1 block font-mono text-xs text-text-2"
                    dateTime={update.occurredAt}
                  >
                    {new Date(update.occurredAt).toLocaleString()}
                  </time>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <p className="text-sm text-text-2">{labels.empty}</p>
      )}
    </section>
  );
}
