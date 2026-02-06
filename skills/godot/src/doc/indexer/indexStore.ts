import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { DocEntry, MemoryIndex, TermEntry } from "../types.js";

export async function saveIndex(outPath: string, index: MemoryIndex): Promise<void> {
  const dir = path.dirname(outPath);
  mkdirSync(dir, { recursive: true });
  const tmp = `${outPath}.tmp`;
  const data = serialize(index);
  writeFileSync(tmp, data);
  renameSync(tmp, outPath);
}

export async function loadIndex(p: string): Promise<MemoryIndex | null> {
  try {
    const text = readFileSync(p, "utf8");
    return deserialize(text);
  } catch {
    return null;
  }
}

function serialize(idx: MemoryIndex): string {
  return JSON.stringify({
    terms: Array.from(idx.terms.entries()),
    docs: Array.from(idx.docs.entries()),
    byQualified: Array.from(idx.byQualified.entries()),
    byClass: Array.from(idx.byClass.entries()),
    docLengths: Array.from(idx.docLengths.entries()),
    stats: idx.stats,
  });
}

function deserialize(text: string): MemoryIndex {
  const j = JSON.parse(text) as {
    terms: [string, TermEntry][];
    docs: [number, DocEntry][];
    byQualified: [string, number][];
    byClass: [string, number[]][];
    docLengths: [number, number][];
    stats: { totalDocs: number; avgDocLen: number };
  };
  return {
    terms: new Map(j.terms),
    docs: new Map(j.docs),
    byQualified: new Map(j.byQualified),
    byClass: new Map(j.byClass),
    docLengths: new Map(j.docLengths),
    stats: j.stats,
  };
}
