import { describe, expect, it } from "vitest";

import {
  groupPaths,
  groupRoutesFromQuery,
  resolveGroupParam,
  resumeTarget,
  type GroupPaymentStatus,
} from "./group-checkout";

const GROUP = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const JOB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const PAY = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";

describe("resolveGroupParam (cart vs group checkout)", () => {
  it("keeps the cart checkout when no group param is present", () => {
    expect(resolveGroupParam(undefined)).toBeUndefined();
    expect(resolveGroupParam({})).toBeUndefined();
    expect(resolveGroupParam({ session: GROUP })).toBeUndefined();
    expect(resolveGroupParam({ kind: "service_deposit" })).toBeUndefined();
  });

  it("enters group mode for ?group= and the legacy service-deposit hand-off", () => {
    expect(resolveGroupParam({ group: GROUP })).toBe(GROUP);
    expect(resolveGroupParam({ group: [GROUP, GROUP] })).toBeNull();
    expect(resolveGroupParam({ session: GROUP, kind: "service_deposit" })).toBe(GROUP);
  });
});

describe("groupPaths", () => {
  it("lands tickets in the wallet and services in the job thread", () => {
    expect(groupPaths("en", GROUP, "ticket", null).success(null)).toBe("/en/account/tickets");
    expect(groupPaths("en", GROUP, "service_deposit", JOB).success("o")).toBe(
      `/en/account/jobs/${JOB}`,
    );
    expect(groupPaths("en", GROUP, "service_deposit", "bad").success("o")).toBe(
      "/en/account/orders/o",
    );
    expect(groupPaths("en", GROUP, "service_deposit", JOB).pending).toBe(
      `/en/checkout/pending/${GROUP}?kind=service_deposit&job=${JOB}`,
    );
  });

  it("builds pending/card routes from query only for known group kinds", () => {
    expect(groupRoutesFromQuery("en", GROUP, {})).toBeUndefined();
    expect(groupRoutesFromQuery("en", "x", { kind: "ticket" })).toBeUndefined();
    expect(groupRoutesFromQuery("en", GROUP, { kind: "ticket" })).toEqual({
      success: "/en/account/tickets",
      checkout: `/en/checkout?group=${GROUP}`,
    });
  });
});

describe("resumeTarget", () => {
  const paths = groupPaths("en", GROUP, "ticket", null);
  const base: GroupPaymentStatus = {
    checkout_group_id: GROUP,
    payment_id: PAY,
    status: "ussd_pushed",
    rail: "mtn",
    cod: false,
    order_id: "o",
  };

  it("resumes waiting attempts and lets terminal failures pick a rail again", () => {
    expect(resumeTarget(null, paths)).toBeNull();
    expect(resumeTarget(base, paths)).toBe(paths.pending);
    expect(resumeTarget({ ...base, rail: "card", status: "initiated" }, paths)).toBe(
      paths.card(PAY),
    );
    expect(resumeTarget({ ...base, status: "success" }, paths)).toBe(paths.pending);
    expect(resumeTarget({ ...base, status: "failed" }, paths)).toBeNull();
    expect(resumeTarget({ ...base, status: "expired" }, paths)).toBeNull();
  });
});
