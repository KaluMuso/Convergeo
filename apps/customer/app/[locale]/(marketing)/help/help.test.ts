import { describe, expect, it } from "vitest";

import {
  buildSearchIndex,
  getAllArticles,
  getArticleBySlug,
  parseFrontmatter,
  toArticle,
} from "./_lib/content";
import { parseBlocks } from "./_lib/markdown";
import { HELP_CATEGORIES, searchArticles } from "./_lib/search";

describe("help frontmatter", () => {
  it("parses frontmatter keys and body", () => {
    const raw = `---\ntitle: Sample\nsummary: A short summary\ncategory: escrow\nkeywords: one, two, three\norder: 5\n---\n\n## Heading\n\nBody text.`;
    const { data, body } = parseFrontmatter(raw);
    expect(data.title).toBe("Sample");
    expect(data.category).toBe("escrow");
    expect(body.startsWith("## Heading")).toBe(true);
  });

  it("builds an article with parsed keywords and defaults", () => {
    const article = toArticle(
      "sample",
      `---\ntitle: Sample\ncategory: buying\nkeywords: alpha, Beta\n---\nHello.`,
    );
    expect(article.slug).toBe("sample");
    expect(article.category).toBe("buying");
    expect(article.keywords).toEqual(["alpha", "beta"]);
    expect(article.order).toBe(100);
  });
});

describe("help content collection", () => {
  it("loads roughly twenty articles with valid categories", () => {
    const articles = getAllArticles();
    expect(articles.length).toBeGreaterThanOrEqual(18);
    for (const article of articles) {
      expect(HELP_CATEGORIES).toContain(article.category);
      expect(article.title.length).toBeGreaterThan(0);
      expect(article.summary.length).toBeGreaterThan(0);
    }
  });

  it("ships a real, substantial escrow flagship article", () => {
    const escrow = getArticleBySlug("how-escrow-works");
    expect(escrow).toBeDefined();
    expect(escrow?.category).toBe("escrow");
    // Real content, not a stub.
    expect(escrow?.body.length ?? 0).toBeGreaterThan(1200);
    expect(escrow?.body.toLowerCase()).toContain("held by vergeo5");
  });
});

describe("help markdown renderer", () => {
  it("parses headings, lists and paragraphs into blocks", () => {
    const blocks = parseBlocks("## Title\n\nA paragraph.\n\n- one\n- two");
    expect(blocks[0]).toMatchObject({ kind: "heading", level: 2 });
    expect(blocks[1]).toMatchObject({ kind: "p" });
    expect(blocks[2]).toMatchObject({ kind: "ul", items: ["one", "two"] });
  });
});

describe("help FAQ search", () => {
  const index = buildSearchIndex();

  it("returns the escrow article for the query 'escrow'", () => {
    const results = searchArticles(index, "escrow");
    expect(results.length).toBeGreaterThan(0);
    expect(results[0]?.slug).toBe("how-escrow-works");
    expect(results.some((doc) => doc.slug === "how-escrow-works")).toBe(true);
  });

  it("finds delivery help for 'delivery' and refunds for 'refund'", () => {
    expect(searchArticles(index, "delivery").some((d) => d.category === "delivery")).toBe(true);
    expect(searchArticles(index, "refund").some((d) => d.category === "returns")).toBe(true);
  });

  it("returns the full index for an empty query and nothing for gibberish", () => {
    expect(searchArticles(index, "")).toHaveLength(index.length);
    expect(searchArticles(index, "zzzqqxnotarealterm")).toHaveLength(0);
  });
});
