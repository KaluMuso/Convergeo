#!/usr/bin/env node
/** Targeted stale-command and local-reference regression check, not shell safety or release proof. */
import console from "node:console";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const RUNBOOKS = ["docs/ops/deploy-verify-runbook.md", "docs/ops/n8n-activation-runbook.md"];
// To retain an explicitly prohibited historical shell example, put this marker
// immediately above its fence. It excludes that entire fence from command checks.
const HISTORICAL_EXAMPLE = "<!-- ops-preflight: historical-do-not-run -->";
const HAZARDS = [
  [/^supabase\s+db\s+push(?:\s|$)/i, "direct hosted migration push"],
  [/^(?:\S*\/)?db-restore\.sh\s+--force(?:\s|$)/i, "unqualified database restore"],
  [/^ssh\s+opc@/i, "historical OCI host"],
  [/^docker\s+compose\s+-f\s+infra\/docker-compose\.yml(?:\s|$)/i, "historical OCI Compose stack"],
  [/^docker\s+compose\s+stop\s+n8n(?:\s|$)/i, "instance-wide n8n stop"],
  [/^docker\s+compose\s+up\s+-d\s+api\s+caddy(?:\s|$)/i, "historical API/Caddy topology"],
  [/^vercel\s+deploy\s+--prod(?:\s|$)/i, "unbound production deploy"],
];

function slug(heading) {
  return heading
    .toLowerCase()
    .replace(/<[^>]*>/g, "")
    .replace(/[^\p{L}\p{N} _-]/gu, "")
    .trim()
    .replace(/\s+/g, "-");
}

function headings(text) {
  const counts = new Map();
  const anchors = [];
  let fence = null;
  for (const line of text.split(/\r?\n/)) {
    const marker = line.match(/^\s*(`{3,}|~{3,})(.*)$/);
    if (marker) {
      if (!fence) fence = { char: marker[1][0], length: marker[1].length };
      else if (marker[1][0] === fence.char && marker[1].length >= fence.length && !marker[2].trim())
        fence = null;
      continue;
    }
    if (fence) continue;
    const match = line.match(/^#{1,6}\s+(.+)$/);
    if (!match) continue;
    const base = slug(match[1]);
    const count = counts.get(base) ?? 0;
    counts.set(base, count + 1);
    anchors.push(count ? `${base}-${count}` : base);
  }
  return anchors;
}

function withoutInlineCode(text) {
  let result = "";
  for (let i = 0; i < text.length;) {
    if (text[i] !== "`") {
      result += text[i++];
      continue;
    }
    let after = i;
    while (text[after] === "`") after++;
    const width = after - i;
    let end = -1;
    for (let next = after; next < text.length;) {
      if (text[next] !== "`") {
        next++;
        continue;
      }
      const start = next;
      while (text[next] === "`") next++;
      if (next - start === width) {
        end = start;
        break;
      }
    }
    if (end < 0) {
      result += text.slice(i, after);
      i = after;
    } else {
      result += " ".repeat(end + width - i);
      i = end + width;
    }
  }
  return result;
}

function destination(raw) {
  const input = raw.trim();
  if (input.startsWith("<")) return input.slice(1, input.indexOf(">"));
  let depth = 0;
  let result = "";
  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (char === "\\" && i + 1 < input.length) {
      result += input[++i];
    } else if (/\s/.test(char) && depth === 0) {
      break;
    } else {
      if (char === "(") depth++;
      if (char === ")") depth--;
      result += char;
    }
  }
  return result;
}

function linkTargets(text) {
  const targets = [];
  for (let i = 0; i < text.length - 1; i++) {
    if (text[i] !== "]" || text[i + 1] !== "(") continue;
    let depth = 1;
    let angle = false;
    let j = i + 2;
    for (; j < text.length; j++) {
      if (text[j] === "\\") {
        j++;
        continue;
      }
      if (text[j] === "<") angle = true;
      if (text[j] === ">") angle = false;
      if (!angle && text[j] === "(") depth++;
      if (!angle && text[j] === ")" && --depth === 0) break;
    }
    if (depth === 0) {
      targets.push(destination(text.slice(i + 2, j)));
      i = j;
    }
  }
  for (const match of text.matchAll(/^ {0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)/gm)) {
    targets.push(destination(match[1]));
  }
  return targets.filter(Boolean);
}

function inspect(root, relPath, errors) {
  const file = resolve(root, relPath);
  if (!existsSync(file)) {
    errors.push(`${relPath}: missing runbook`);
    return;
  }
  const lines = readFileSync(file, "utf8").split(/\r?\n/);
  const prose = [];
  let fence = null;
  for (const [index, line] of lines.entries()) {
    const marker = line.match(/^\s*(`{3,}|~{3,})(.*)$/);
    if (marker) {
      if (!fence)
        fence = {
          char: marker[1][0],
          length: marker[1].length,
          shell:
            /^(?:bash|sh|shell|zsh|console)\b/i.test(marker[2].trim()) &&
            lines[index - 1]?.trim() !== HISTORICAL_EXAMPLE,
        };
      else if (marker[1][0] === fence.char && marker[1].length >= fence.length && !marker[2].trim())
        fence = null;
      continue;
    }
    if (!fence) {
      prose.push(line);
      continue;
    }
    if (!fence.shell) continue;
    const command = line
      .trim()
      .replace(/^\$\s*/, "")
      .replace(/^sudo\s+/, "");
    if (!command || command.startsWith("#")) continue;
    for (const [pattern, reason] of HAZARDS) {
      if (pattern.test(command)) errors.push(`${relPath}:${index + 1}: ${reason}`);
    }
  }
  if (fence) errors.push(`${relPath}: unclosed code fence`);

  for (const target of linkTargets(withoutInlineCode(prose.join("\n")))) {
    if (/^[a-z][a-z\d+.-]*:/i.test(target)) continue;
    const [path, fragment] = target.split("#", 2);
    let linked;
    try {
      linked = resolve(dirname(file), decodeURIComponent(path || relPath.split("/").at(-1)));
    } catch {
      errors.push(`${relPath}: invalid local link ${target}`);
      continue;
    }
    if (
      isAbsolute(path) ||
      relative(root, linked).startsWith("..") ||
      !existsSync(linked) ||
      !statSync(linked).isFile()
    ) {
      errors.push(`${relPath}: missing or escaping local link ${target}`);
      continue;
    }
    if (fragment) {
      const anchors = headings(readFileSync(linked, "utf8"));
      try {
        if (!anchors.includes(decodeURIComponent(fragment)))
          errors.push(`${relPath}: missing heading ${target}`);
      } catch {
        errors.push(`${relPath}: invalid heading link ${target}`);
      }
    }
  }
}

export function checkRunbooks(root) {
  const errors = [];
  for (const relPath of RUNBOOKS) inspect(root, relPath, errors);
  return errors;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const root =
    process.argv.length === 2
      ? resolve(dirname(fileURLToPath(import.meta.url)), "../..")
      : process.argv[2] === "--root" && process.argv.length === 4
        ? resolve(process.argv[3])
        : null;
  if (!root) {
    console.error("usage: node scripts/ci/check-ops-runbook-preflight.mjs [--root REPO]");
    process.exitCode = 2;
  } else {
    const errors = checkRunbooks(root);
    for (const error of errors) console.error(error);
    if (errors.length) process.exitCode = 1;
    else console.log("ops runbook preflight: PASS");
  }
}
