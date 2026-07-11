import type { ReactNode } from "react";

/**
 * Minimal, dependency-free Markdown renderer for founder-editable Help articles.
 * Builds React elements directly (never dangerouslySetInnerHTML) so article content
 * cannot inject markup. Supports the subset used by Help content: headings, ordered
 * and unordered lists, blockquotes, fenced code, paragraphs, and inline bold / italic
 * / code / links.
 */

type Block =
  | { kind: "heading"; level: 2 | 3 | 4; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; text: string }
  | { kind: "p"; text: string };

const HEADING = /^(#{1,6})\s+(.*)$/;
const UL_ITEM = /^[-*]\s+(.*)$/;
const OL_ITEM = /^\d+\.\s+(.*)$/;
const QUOTE = /^>\s?(.*)$/;
const FENCE = /^```/;

/** Return the captured item text for `re` against `line`, or null if it does not match. */
function matchItem(re: RegExp, line: string): string | null {
  const match = re.exec(line);
  return match ? (match[1] ?? "").trim() : null;
}

export function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];

  const flushParagraph = (): void => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "p", text: paragraph.join(" ").trim() });
      paragraph = [];
    }
  };

  const collectItems = (
    re: RegExp,
    startIndex: number,
    first: string,
  ): { items: string[]; end: number } => {
    const items = [first];
    let index = startIndex;
    while (index + 1 < lines.length) {
      const next = matchItem(re, (lines[index + 1] ?? "").trim());
      if (next === null) {
        break;
      }
      items.push(next);
      index += 1;
    }
    return { items, end: index };
  };

  for (let i = 0; i < lines.length; i += 1) {
    const trimmed = (lines[i] ?? "").trim();

    if (FENCE.test(trimmed)) {
      flushParagraph();
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !FENCE.test((lines[i] ?? "").trim())) {
        code.push(lines[i] ?? "");
        i += 1;
      }
      blocks.push({ kind: "code", text: code.join("\n") });
      continue;
    }

    if (trimmed.length === 0) {
      flushParagraph();
      continue;
    }

    const heading = HEADING.exec(trimmed);
    if (heading) {
      flushParagraph();
      const level = Math.min(4, Math.max(2, (heading[1] ?? "").length)) as 2 | 3 | 4;
      blocks.push({ kind: "heading", level, text: (heading[2] ?? "").trim() });
      continue;
    }

    const ulText = matchItem(UL_ITEM, trimmed);
    if (ulText !== null) {
      flushParagraph();
      const { items, end } = collectItems(UL_ITEM, i, ulText);
      i = end;
      blocks.push({ kind: "ul", items });
      continue;
    }

    const olText = matchItem(OL_ITEM, trimmed);
    if (olText !== null) {
      flushParagraph();
      const { items, end } = collectItems(OL_ITEM, i, olText);
      i = end;
      blocks.push({ kind: "ol", items });
      continue;
    }

    const quoteText = matchItem(QUOTE, trimmed);
    if (quoteText !== null) {
      flushParagraph();
      const { items, end } = collectItems(QUOTE, i, quoteText);
      i = end;
      blocks.push({ kind: "quote", text: items.join(" ") });
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  return blocks;
}

const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  INLINE.lastIndex = 0;

  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0] ?? "";
    if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(
        <code key={key} className="rounded bg-bg-2 px-1 py-0.5 font-mono text-sm">
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("[")) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (linkMatch) {
        nodes.push(
          <a
            key={key}
            className="text-primary underline underline-offset-2"
            href={linkMatch[2] ?? "#"}
            rel="noopener noreferrer"
          >
            {linkMatch[1] ?? ""}
          </a>,
        );
      } else {
        nodes.push(token);
      }
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    lastIndex = match.index + token.length;
    key += 1;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

export function Markdown({ content }: { content: string }): ReactNode {
  const blocks = parseBlocks(content);

  return (
    <div className="space-y-4 text-body leading-relaxed text-text">
      {blocks.map((block, index) => {
        const key = `${block.kind}-${index}`;
        switch (block.kind) {
          case "heading": {
            if (block.level === 2) {
              return (
                <h2 key={key} className="font-display text-h2 text-display-ink">
                  {renderInline(block.text)}
                </h2>
              );
            }
            if (block.level === 3) {
              return (
                <h3 key={key} className="font-display text-h3 text-display-ink">
                  {renderInline(block.text)}
                </h3>
              );
            }
            return (
              <h4 key={key} className="font-body text-lg font-semibold text-text">
                {renderInline(block.text)}
              </h4>
            );
          }
          case "ul":
            return (
              <ul key={key} className="list-disc space-y-1 ps-5">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex}>{renderInline(item)}</li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={key} className="list-decimal space-y-1 ps-5">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex}>{renderInline(item)}</li>
                ))}
              </ol>
            );
          case "quote":
            return (
              <blockquote
                key={key}
                className="border-s-4 border-primary/40 bg-bg-2 px-4 py-2 text-text-2"
              >
                {renderInline(block.text)}
              </blockquote>
            );
          case "code":
            return (
              <pre
                key={key}
                className="overflow-x-auto rounded-lg bg-bg-2 p-4 font-mono text-sm text-text"
              >
                <code>{block.text}</code>
              </pre>
            );
          default:
            return (
              <p key={key} className="text-body">
                {renderInline(block.text)}
              </p>
            );
        }
      })}
    </div>
  );
}
