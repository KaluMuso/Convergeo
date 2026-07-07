#!/usr/bin/env node
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";

const requiredFiles = [
  "package.json",
  "pnpm-workspace.yaml",
  "turbo.json",
  "tsconfig.base.json",
  "eslint.config.mjs",
  ".env.example",
  "commitlint.config.cjs",
  "lefthook.yml",
];

function run(command) {
  execSync(command, { stdio: "inherit", env: process.env });
}

function assertCommitlint(message, shouldPass) {
  try {
    execSync(`echo "${message}" | pnpm exec commitlint`, {
      stdio: "pipe",
      env: process.env,
    });
    if (!shouldPass) {
      throw new Error(`Expected commitlint to reject: ${message}`);
    }
  } catch (error) {
    if (shouldPass) {
      throw new Error(`Expected commitlint to accept: ${message}`);
    }
  }
}

console.log("verify-scaffold: checking required files...");
for (const file of requiredFiles) {
  if (!existsSync(file)) {
    throw new Error(`Missing required file: ${file}`);
  }
}

console.log("verify-scaffold: pnpm lint...");
run("pnpm lint");

console.log("verify-scaffold: pnpm typecheck...");
run("pnpm typecheck");

console.log("verify-scaffold: commitlint rejection...");
assertCommitlint("bad message", false);

console.log("verify-scaffold: commitlint acceptance...");
assertCommitlint("feat: ok", true);

console.log("verify-scaffold: all checks passed");
