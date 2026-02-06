import type { DocEntry, GodotClassDoc, MemoryIndex, TermEntry } from "../types.js";

function tokenizeText(s: string = ""): string[] {
  return String(s)
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, " ")
    .split(/\s+/)
    .filter((t) => t.length >= 2);
}

export function tokenizeName(name: string = ""): string[] {
  const raw = String(name);
  const parts: string[] = [];
  // Insert boundaries for common cases:
  // 1) Acronym→Word: HTTPRequest -> HTTP Request
  // 2) lower/digit→Upper: camera3D -> camera 3D, fooBar -> foo Bar
  // 3) Letter↔Digit both directions: GLTF2Importer -> GLTF 2 Importer, Array2D -> Array 2 D
  const separated = raw
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Za-z])([0-9])/g, "$1 $2")
    // Only split digit→letter when it begins a Capitalized word (keep 3D intact)
    .replace(/([0-9])([A-Z][a-z])/g, "$1 $2");

  const toks = separated.split(/[^A-Za-z0-9]+/).filter(Boolean);
  for (const t of toks) parts.push(t.toLowerCase());
  // Also include the compact concat form (e.g., 'httprequest', 'cpuparticles3d')
  const combo = toks.join("").toLowerCase();
  if (combo && !parts.includes(combo)) parts.push(combo);
  return parts;
}

function docTokens(entry: DocEntry): string[] {
  const tokens: string[] = [];
  tokens.push(...tokenizeName(entry.name));
  if (entry.brief) tokens.push(...tokenizeText(entry.brief));
  if (entry.description) tokens.push(...tokenizeText(entry.description));
  return tokens;
}

export function buildIndex(classes: GodotClassDoc[]): MemoryIndex {
  let nextId = 1;
  const docs = new Map<number, DocEntry>();
  const byQualified = new Map<string, number>();
  const byClass = new Map<string, number[]>();
  const termMap = new Map<string, TermEntry>();
  const docLengths = new Map<number, number>();
  const lengths: number[] = [];

  function addDoc(entry: Omit<DocEntry, "id">): number {
    const id = nextId++;
    const full: DocEntry = { id, ...entry };
    docs.set(id, full);
    const tks = docTokens(full);
    const len = Math.max(1, tks.length);
    lengths.push(len);
    docLengths.set(id, len);
    const tfCount = new Map<string, number>();
    for (const t of tks) tfCount.set(t, (tfCount.get(t) || 0) + 1);
    for (const [t, tf] of tfCount) {
      let te = termMap.get(t);
      if (!te) {
        te = { term: t, postings: [], df: 0 };
        termMap.set(t, te);
      }
      te.postings.push({ docId: id, tf });
      te.df++;
    }
    return id;
  }

  for (const c of classes) {
    const classDocId = addDoc({
      kind: "class",
      name: c.name,
      brief: c.brief,
      description: c.description,
    });
    byClass.set(c.name, [classDocId]);
    for (const m of c.methods || []) {
      const id = addDoc({
        kind: "method",
        name: m.name,
        className: c.name,
        brief: m.description,
        description: m.description,
      });
      byQualified.set(`${c.name}.${m.name}`, id);
      const arrM = byClass.get(c.name);
      if (arrM) arrM.push(id);
    }
    for (const p of c.properties || []) {
      const id = addDoc({
        kind: "property",
        name: p.name,
        className: c.name,
        brief: p.description,
        description: p.description,
      });
      byQualified.set(`${c.name}.${p.name}`, id);
      const arrP = byClass.get(c.name);
      if (arrP) arrP.push(id);
    }
    for (const s of c.signals || []) {
      const id = addDoc({
        kind: "signal",
        name: s.name,
        className: c.name,
        brief: s.description,
        description: s.description,
      });
      byQualified.set(`${c.name}.${s.name}`, id);
      const arrS = byClass.get(c.name);
      if (arrS) arrS.push(id);
    }
    for (const k of c.constants || []) {
      const id = addDoc({
        kind: "constant",
        name: k.name,
        className: c.name,
        brief: k.description,
        description: k.description,
      });
      byQualified.set(`${c.name}.${k.name}`, id);
      const arrK = byClass.get(c.name);
      if (arrK) arrK.push(id);
    }
  }

  const totalDocs = docs.size;
  const avgDocLen = lengths.reduce((a, b) => a + b, 0) / Math.max(1, lengths.length);

  return {
    terms: termMap,
    docs,
    byQualified,
    byClass,
    docLengths,
    stats: { totalDocs, avgDocLen },
  } as MemoryIndex;
}

export function scoreQuery(index: MemoryIndex, queryTokens: string[]): Map<number, number> {
  const N = index.stats.totalDocs || 1;
  const k1 = 1.5,
    b = 0.75;
  const avgdl = index.stats.avgDocLen || 1;
  const scores = new Map<number, number>();
  for (const q of queryTokens) {
    const te = index.terms.get(q);
    if (!te) continue;
    const idf = Math.log(1 + (N - te.df + 0.5) / (te.df + 0.5));
    for (const { docId, tf } of te.postings) {
      const dl = index.docLengths.get(docId) ?? avgdl;
      const denom = tf + k1 * (1 - b + b * (dl / avgdl));
      const sc = idf * ((tf * (k1 + 1)) / denom);
      scores.set(docId, (scores.get(docId) || 0) + sc);
    }
  }
  return scores;
}
