import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { cookiesMock, createServerClientMock } = vi.hoisted(() => ({
  cookiesMock: vi.fn(),
  createServerClientMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: cookiesMock,
}));

vi.mock("@vergeo/auth/server-client", () => ({
  createServerClient: createServerClientMock,
}));

import { fetchCategories, fetchCategoriesResult } from "./merch-data";

type QueryResult = {
  data: unknown;
  error: { code?: string; message?: string } | null;
  status?: number;
};

function mockQuery(result: QueryResult) {
  const order = vi.fn().mockResolvedValue(result);
  const eq = vi.fn().mockReturnValue({ order });
  const select = vi.fn().mockReturnValue({ eq });
  const from = vi.fn().mockReturnValue({ select });
  createServerClientMock.mockReturnValue({ from });
  cookiesMock.mockResolvedValue({ getAll: () => [], set: () => undefined });
  return { from, select, eq, order };
}

describe("fetchCategoriesResult", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns populated rows on success", async () => {
    mockQuery({
      data: [
        {
          id: "electronics",
          name: "Electronics",
          slug: "electronics",
          path: "electronics",
          position: 1,
          parent_id: null,
          prohibited: false,
        },
      ],
      error: null,
      status: 200,
    });

    await expect(fetchCategoriesResult()).resolves.toEqual({
      ok: true,
      categories: [
        {
          id: "electronics",
          name: "Electronics",
          slug: "electronics",
          path: "electronics",
          position: 1,
          parent_id: null,
          prohibited: false,
        },
      ],
    });
  });

  it("returns an honest empty success when the catalogue has no rows", async () => {
    mockQuery({ data: [], error: null, status: 200 });
    await expect(fetchCategoriesResult()).resolves.toEqual({ ok: true, categories: [] });
  });

  it("returns malformed when every row fails validation", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockQuery({ data: [{ id: 1 }, { foo: "bar" }], error: null, status: 200 });

    await expect(fetchCategoriesResult()).resolves.toEqual({
      ok: false,
      reason: "malformed",
    });
    expect(errorSpy).toHaveBeenCalled();
  });

  it("returns unauthorized for permission / JWT failures", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockQuery({
      data: null,
      error: { code: "PGRST301", message: "JWT expired" },
      status: 401,
    });

    await expect(fetchCategoriesResult()).resolves.toEqual({
      ok: false,
      reason: "unauthorized",
      code: "PGRST301",
      status: 401,
    });
    expect(JSON.parse(String(errorSpy.mock.calls[0]?.[0])).reason).toBe("unauthorized");
  });

  it("returns upstream for generic Supabase failures", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockQuery({
      data: null,
      error: { code: "PGRST002", message: "schema cache" },
      status: 503,
    });

    await expect(fetchCategoriesResult()).resolves.toEqual({
      ok: false,
      reason: "upstream",
      code: "PGRST002",
      status: 503,
    });
    expect(errorSpy).toHaveBeenCalled();
  });

  it("returns config when the server client cannot be created", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    cookiesMock.mockResolvedValue({ getAll: () => [], set: () => undefined });
    createServerClientMock.mockImplementation(() => {
      throw new Error("Missing required environment variable: NEXT_PUBLIC_SUPABASE_URL");
    });

    await expect(fetchCategoriesResult()).resolves.toEqual({
      ok: false,
      reason: "config",
    });
    expect(errorSpy).toHaveBeenCalled();
  });

  it("keeps fetchCategories as a degrading convenience wrapper", async () => {
    mockQuery({
      data: null,
      error: { code: "PGRST002", message: "schema cache" },
      status: 503,
    });
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    await expect(fetchCategories()).resolves.toEqual([]);
  });
});
