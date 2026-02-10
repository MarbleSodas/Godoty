#!/usr/bin/env bun
/**
 * Build script for bundled MCP servers.
 *
 * Pipeline:
 *   1. Build the skill TypeScript (tsc + copy GDScripts)
 *   2. esbuild both servers into self-contained ESM bundles
 *   3. Copy GDScript files to resources
 *   4. Copy Godot doc XMLs to resources
 *
 * Usage:
 *   bun scripts/build-mcp.ts                # full build
 *   bun scripts/build-mcp.ts --skip-docs    # skip 892 XML copies (faster iteration)
 */

import { existsSync } from "node:fs";
import { cp, mkdir, readdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { execSync } from "node:child_process";

const ROOT = resolve(import.meta.dirname, "..");
const SKILL_DIR = join(ROOT, "skills", "godot");
const RESOURCES = join(ROOT, "src-tauri", "resources");
const GODOT_SERVER_OUT = join(RESOURCES, "mcp-servers", "godot", "server.js");
const DOC_SERVER_OUT = join(RESOURCES, "mcp-servers", "godot-doc", "doc-server.js");
const SCRIPTS_OUT = join(RESOURCES, "mcp-servers", "godot", "scripts");
const DOCS_OUT = join(RESOURCES, "godot_docs", "classes");

// External Godot doc XMLs (authoritative source)
const DOC_SOURCE = resolve(
  process.env.GODOT_DOC_SOURCE ??
    join(process.env.HOME!, "mcp-servers", "godot-doc-mcp", "doc", "classes")
);

const skipDocs = process.argv.includes("--skip-docs");

function run(cmd: string, cwd?: string) {
  console.log(`  $ ${cmd}`);
  execSync(cmd, { cwd, stdio: "inherit" });
}

async function ensureDir(dir: string) {
  if (!existsSync(dir)) await mkdir(dir, { recursive: true });
}

// ─── Step 1: TypeScript build ───────────────────────────────────────
console.log("\n[1/4] Building skill TypeScript...");
run("npx tsc", SKILL_DIR);
await ensureDir(join(SKILL_DIR, "dist", "scripts"));
run("cp scripts/*.gd dist/scripts/", SKILL_DIR);

// ─── Step 2: esbuild bundles ────────────────────────────────────────
console.log("\n[2/4] Bundling MCP servers with esbuild...");
await ensureDir(join(RESOURCES, "mcp-servers", "godot"));
await ensureDir(join(RESOURCES, "mcp-servers", "godot-doc"));

run(
  `npx esbuild src/server.ts --bundle --platform=node --target=node20 --format=esm --outfile="${GODOT_SERVER_OUT}"`,
  SKILL_DIR
);
run(
  `npx esbuild src/doc-server.ts --bundle --platform=node --target=node20 --format=esm --outfile="${DOC_SERVER_OUT}"`,
  SKILL_DIR
);

// ─── Step 3: GDScript files ─────────────────────────────────────────
console.log("\n[3/4] Copying GDScript files...");
await ensureDir(SCRIPTS_OUT);
const gdScripts = ["godot_operations.gd", "viewport_capture.gd"];
for (const gd of gdScripts) {
  const src = join(SKILL_DIR, "scripts", gd);
  if (existsSync(src)) {
    await cp(src, join(SCRIPTS_OUT, gd));
    console.log(`  Copied ${gd}`);
  } else {
    console.warn(`  WARNING: ${gd} not found at ${src}`);
  }
}

// ─── Step 4: Godot doc XMLs ────────────────────────────────────────
if (skipDocs) {
  console.log("\n[4/4] Skipping Godot doc XMLs (--skip-docs)");
} else {
  console.log("\n[4/4] Copying Godot doc XMLs...");
  if (!existsSync(DOC_SOURCE)) {
    console.error(`  ERROR: Doc source not found: ${DOC_SOURCE}`);
    console.error(
      `  Set GODOT_DOC_SOURCE env var or ensure ${DOC_SOURCE} exists`
    );
    process.exit(1);
  }
  await ensureDir(DOCS_OUT);
  const entries = await readdir(DOC_SOURCE);
  const xmlFiles = entries.filter((f) => f.endsWith(".xml"));
  let count = 0;
  for (const xml of xmlFiles) {
    await cp(join(DOC_SOURCE, xml), join(DOCS_OUT, xml));
    count++;
  }
  console.log(`  Copied ${count} XML doc files`);
}

console.log("\nMCP build complete!");
console.log(`  Godot server:  ${GODOT_SERVER_OUT}`);
console.log(`  Doc server:    ${DOC_SERVER_OUT}`);
console.log(`  GDScripts:     ${SCRIPTS_OUT}/`);
if (!skipDocs) console.log(`  Godot docs:    ${DOCS_OUT}/`);
