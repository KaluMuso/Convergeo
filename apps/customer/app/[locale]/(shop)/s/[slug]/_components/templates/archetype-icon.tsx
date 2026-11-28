import {
  LcDumbbell,
  LcHome,
  LcSparkles,
  LcTicket,
  LcUsers,
  LcWrench,
  LcCar,
} from "@vergeo/ui/src/lucide-icons";

import type { Archetype } from "../../_lib/archetypes";

export function ArchetypeIcon({
  archetype,
  className,
}: {
  archetype: Archetype;
  className?: string;
}) {
  const props = { className, "aria-hidden": true as const };
  switch (archetype) {
    case "accommodation":
      return <LcHome {...props} />;
    case "appointment":
      return <LcSparkles {...props} />;
    case "membership":
      return <LcDumbbell {...props} />;
    case "on_site":
      return <LcWrench {...props} />;
    case "rental":
      return <LcCar {...props} />;
    case "ticketed":
      return <LcTicket {...props} />;
    default:
      return <LcUsers {...props} />;
  }
}
