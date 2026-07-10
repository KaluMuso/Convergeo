import { Badge } from "@vergeo/ui/src/badge";

export type ReturnableBadgeProps = {
  returnable: boolean;
  returnWindowHours: number;
  label: string;
};

function windowDays(returnWindowHours: number): number {
  return Math.max(1, Math.ceil(returnWindowHours / 24));
}

export function ReturnableBadge({ returnable, returnWindowHours, label }: ReturnableBadgeProps) {
  if (!returnable) {
    return null;
  }

  const days = windowDays(returnWindowHours);
  const resolvedLabel = label.replace("{days}", String(days));

  return (
    <span className="inline-flex min-h-[22px] shrink-0 items-center" data-testid="returnable-badge">
      <Badge variant="public" label={resolvedLabel} />
    </span>
  );
}
