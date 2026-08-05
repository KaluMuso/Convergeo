import { Badge } from "@vergeo/ui/src/badge";

export type ListingCondition = "new" | "refurbished" | "used";

export type ConditionBadgeProps = {
  condition: ListingCondition;
  label: string;
};

export function ConditionBadge({ condition, label }: ConditionBadgeProps) {
  const variant = condition === "new" ? "new" : "featured";

  return <Badge variant={variant} label={label} />;
}
