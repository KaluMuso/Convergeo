import { ARCHETYPES, type Archetype } from "./archetypes";

import type { RequestPanelLabels } from "../_components/templates/request-panel";
import type { T } from "../_components/templates/shared";

/** Collects the request panel strings (plain data) for one archetype from `services.templates`. */
export function buildPanelLabels(t: T, archetype: Archetype): RequestPanelLabels {
  const startDate = Object.fromEntries(
    ARCHETYPES.map((key) => [key, t(`request.startDate.${key}`)]),
  ) as Record<Archetype, string>;
  const timeOfDay = Object.fromEntries(
    ["any", "morning", "afternoon", "evening"].map((key) => [key, t(`request.timeOfDay.${key}`)]),
  );
  const periods = Object.fromEntries(
    ["hour", "day", "week"].map((key) => [
      key,
      {
        one: t(`request.periods.${key}.one`, { count: "{count}" }),
        many: t(`request.periods.${key}.many`, { count: "{count}" }),
      },
    ]),
  );
  return {
    heading: t(`request.heading.${archetype}`),
    cta: t(`request.cta.${archetype}`),
    fix: t("request.fix"),
    chooseOffer: t("request.chooseOffer"),
    selectOffer: t("request.selectOffer"),
    startDate,
    endDate: t("request.endDate"),
    time: t("request.time"),
    guests: t("request.guests"),
    quantity: t("request.quantity"),
    period: t("request.period"),
    staff: t("request.staff"),
    anyStaff: t("request.anyStaff"),
    timeOfDay,
    nightsOne: t("request.nightsOne", { count: "{count}" }),
    nightsMany: t("request.nightsMany", { count: "{count}" }),
    periods,
    errors: {
      pickOffer: t("request.errors.pickOffer"),
      pickDate: t("request.errors.pickDate"),
      pickEnd: t("request.errors.pickEnd"),
      endBeforeStart: t("request.errors.endBeforeStart"),
      pastDate: t("request.errors.pastDate"),
    },
    noPaymentNote: t("request.noPaymentNote"),
    dialogTitle: t("request.dialogTitle", { name: "{name}" }),
  };
}
