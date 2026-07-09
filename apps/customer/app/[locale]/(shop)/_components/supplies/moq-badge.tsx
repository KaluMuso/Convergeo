import { Badge } from "@vergeo/ui/src/badge";

export type MoqBadgeProps = {
  moq: number;
  label: string;
};

export function MoqBadge({ moq, label }: MoqBadgeProps) {
  return (
    <span data-testid="supplies-moq-badge">
      <Badge variant="public" label={label.replace("{qty}", String(moq))} className="shrink-0" />
    </span>
  );
}
