import { describe, expect, it } from "vitest";

import {
  OFFER_FIELDS,
  SERVICE_FIELDS,
  attributesFromValues,
  deriveArchetype,
  effectiveArchetype,
  emptyValues,
  valuesFromAttributes,
} from "./archetypes";
import { draftFromPackage, emptyDraft, validateDraft, type ServicePackage } from "./packages";

const toZmw = (n: number) => (n / 100).toFixed(2);

describe("archetype derivation", () => {
  it("maps verticals and falls back to professional", () => {
    expect(deriveArchetype("lodging")).toBe("accommodation");
    expect(deriveArchetype("beauty")).toBe("appointment");
    expect(deriveArchetype("fitness")).toBe("membership");
    expect(deriveArchetype("rentals")).toBe("rental");
    expect(deriveArchetype("unknown")).toBe("professional");
    expect(deriveArchetype(null)).toBe("professional");
  });

  it("prefers a valid override", () => {
    expect(effectiveArchetype("rental", "lodging")).toBe("rental");
    expect(effectiveArchetype(null, "lodging")).toBe("accommodation");
  });
});

describe("attributesFromValues", () => {
  it("omits empty fields and converts types", () => {
    const defs = OFFER_FIELDS.accommodation;
    const values = emptyValues(defs);
    values.sleeps = "3";
    values.breakfast_included = true;
    values.amenities = "Wi-Fi, Parking";
    const result = attributesFromValues(defs, values);
    expect(result).toEqual({
      ok: true,
      attributes: {
        sleeps: 3,
        breakfast_included: true,
        amenities: ["Wi-Fi", "Parking"],
      },
    });
  });

  it("converts rental deposit ZMW to integer ngwee", () => {
    const defs = OFFER_FIELDS.rental;
    const values = emptyValues(defs);
    values.deposit_ngwee = "150.50";
    const result = attributesFromValues(defs, values);
    expect(result).toEqual({ ok: true, attributes: { deposit_ngwee: 15_050 } });
  });

  it("rejects out-of-range, non-numeric and off-step values", () => {
    const acc = emptyValues(OFFER_FIELDS.accommodation);
    acc.sleeps = "99";
    expect(attributesFromValues(OFFER_FIELDS.accommodation, acc)).toMatchObject({
      ok: false,
      errors: { sleeps: "int" },
    });
    const appt = emptyValues(OFFER_FIELDS.appointment);
    appt.duration_min = "32";
    expect(attributesFromValues(OFFER_FIELDS.appointment, appt)).toMatchObject({
      ok: false,
      errors: { duration_min: "step" },
    });
    const frac = emptyValues(OFFER_FIELDS.accommodation);
    frac.beds = "1.5";
    expect(attributesFromValues(OFFER_FIELDS.accommodation, frac).ok).toBe(false);
  });

  it("rejects bad money and bad times", () => {
    const rent = emptyValues(OFFER_FIELDS.rental);
    rent.deposit_ngwee = "0";
    expect(attributesFromValues(OFFER_FIELDS.rental, rent).ok).toBe(false);
    const svc = emptyValues(SERVICE_FIELDS.accommodation);
    svc.check_in = "25:00";
    expect(attributesFromValues(SERVICE_FIELDS.accommodation, svc)).toMatchObject({
      ok: false,
      errors: { check_in: "time" },
    });
    svc.check_in = "14:00";
    expect(attributesFromValues(SERVICE_FIELDS.accommodation, svc).ok).toBe(true);
  });

  it("enforces age order and incomplete rows", () => {
    const defs = OFFER_FIELDS.ticketed;
    const values = emptyValues(defs);
    values.age_min = "10";
    values.age_max = "5";
    expect(attributesFromValues(defs, values)).toMatchObject({
      ok: false,
      errors: { age_max: "ageOrder" },
    });
    const rent = emptyValues(OFFER_FIELDS.rental);
    rent.specs = [{ label: "Seats", value: "" }];
    expect(attributesFromValues(OFFER_FIELDS.rental, rent)).toMatchObject({
      ok: false,
      errors: { specs: "rows" },
    });
    rent.specs = [{ label: "Seats", value: "5" }];
    expect(attributesFromValues(OFFER_FIELDS.rental, rent)).toEqual({
      ok: true,
      attributes: { specs: [{ label: "Seats", value: "5" }] },
    });
  });

  it("round-trips through valuesFromAttributes", () => {
    const defs = OFFER_FIELDS.rental;
    const attrs = {
      unit: "day",
      deposit_ngwee: 20_000,
      specs: [{ label: "Seats", value: "5" }],
      with_operator: true,
    };
    const values = valuesFromAttributes(defs, attrs, toZmw);
    expect(values.deposit_ngwee).toBe("200.00");
    expect(attributesFromValues(defs, values)).toEqual({ ok: true, attributes: attrs });
  });

  it("ignores unknown or mistyped stored values", () => {
    const values = valuesFromAttributes(
      OFFER_FIELDS.accommodation,
      { sleeps: { a: 1 }, amenities: [1, "Pool"], junk: true },
      toZmw,
    );
    expect(values.amenities).toBe("Pool");
    expect(attributesFromValues(OFFER_FIELDS.accommodation, values).ok).toBe(true);
  });
});

describe("package drafts with attributes", () => {
  const pkg: ServicePackage = {
    id: "p1",
    tier: null,
    name: "Deluxe room",
    description: null,
    price_ngwee: 120_000,
    delivery_days: 1,
    revisions: null,
    includes: [],
    sort_order: 0,
    status: "active",
    updated_at: null,
    attributes: { sleeps: 3, breakfast_included: true },
  };

  it("loads attributes into the draft and sends them back", () => {
    const draft = draftFromPackage(pkg, toZmw, "accommodation");
    expect(draft.attributes.sleeps).toBe("3");
    const result = validateDraft(draft, "accommodation");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload.attributes).toEqual({ sleeps: 3, breakfast_included: true });
      expect(result.payload.price_ngwee).toBe(120_000);
    }
  });

  it("surfaces attribute errors", () => {
    const draft = emptyDraft("accommodation");
    draft.name = "Room";
    draft.price = "100";
    draft.attributes.sleeps = "500";
    const result = validateDraft(draft, "accommodation");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.attributeErrors?.sleeps).toBe("int");
  });
});
