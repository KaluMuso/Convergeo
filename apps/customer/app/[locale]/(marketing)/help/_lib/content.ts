import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { isHelpCategory, type HelpCategory, type HelpSearchDoc } from "./search";

export { HELP_CATEGORIES, type HelpCategory, type HelpSearchDoc } from "./search";

export type HelpArticle = {
  slug: string;
  title: string;
  summary: string;
  category: HelpCategory;
  keywords: string[];
  order: number;
  body: string;
};

// Resolve from this module (not process.cwd) so SSG workers and vitest both find
// apps/customer/content/help regardless of launch directory.
const CONTENT_DIR = join(dirname(fileURLToPath(import.meta.url)), "../../../../../content/help");

/**
 * Parse a tiny YAML-ish frontmatter block delimited by `---`.
 * Supports `key: value` scalars and comma-separated `keywords`.
 */
export function parseFrontmatter(raw: string): { data: Record<string, string>; body: string } {
  const normalised = raw.replace(/\r\n/g, "\n");
  const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(normalised);
  if (!match) {
    return { data: {}, body: normalised.trim() };
  }

  const frontmatter = match[1] ?? "";
  const rest = match[2] ?? "";
  const data: Record<string, string> = {};
  for (const line of frontmatter.split("\n")) {
    const colon = line.indexOf(":");
    if (colon === -1) {
      continue;
    }
    const key = line.slice(0, colon).trim();
    let value = line.slice(colon + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key) {
      data[key] = value;
    }
  }

  return { data, body: rest.trim() };
}

export function toArticle(slug: string, raw: string): HelpArticle {
  const { data, body } = parseFrontmatter(raw);
  const category = isHelpCategory(data.category ?? "") ? (data.category as HelpCategory) : "buying";
  const keywords = (data.keywords ?? "")
    .split(",")
    .map((keyword) => keyword.trim().toLowerCase())
    .filter((keyword) => keyword.length > 0);

  return {
    slug,
    title: data.title ?? slug,
    summary: data.summary ?? "",
    category,
    keywords,
    order: Number.parseInt(data.order ?? "100", 10) || 100,
    body,
  };
}

let cache: HelpArticle[] | undefined;

export function getAllArticles(): HelpArticle[] {
  if (cache) {
    return cache;
  }

  const files = readdirSync(CONTENT_DIR).filter((file) => file.endsWith(".mdx"));
  const articles = files.map((file) => {
    const slug = file.replace(/\.mdx$/, "");
    return toArticle(slug, readFileSync(`${CONTENT_DIR}/${file}`, "utf8"));
  });

  articles.sort((a, b) => a.order - b.order || a.title.localeCompare(b.title));
  cache = articles;
  return articles;
}

export function getArticleSlugs(): string[] {
  return getAllArticles().map((article) => article.slug);
}

export function getArticleBySlug(slug: string): HelpArticle | undefined {
  return getAllArticles().find((article) => article.slug === slug);
}

export function getRelatedArticles(article: HelpArticle, limit = 3): HelpArticle[] {
  return getAllArticles()
    .filter((other) => other.slug !== article.slug && other.category === article.category)
    .slice(0, limit);
}

export function toSearchDoc(article: HelpArticle): HelpSearchDoc {
  return {
    slug: article.slug,
    title: article.title,
    summary: article.summary,
    category: article.category,
    keywords: article.keywords,
  };
}

export function buildSearchIndex(articles: HelpArticle[] = getAllArticles()): HelpSearchDoc[] {
  return articles.map(toSearchDoc);
}
