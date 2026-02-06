import { scoreQuery, tokenizeName } from "../indexer/indexBuilder.js";
import type { MemoryIndex } from "../types.js";

export interface SearchEngine {
  search(input: {
    query: string;
    kind?: "class" | "method" | "property" | "signal" | "constant";
    limit?: number;
  }): Array<{ uri: string; name: string; kind: string; score: number; snippet?: string }>;
}

export function createSearchEngine(index: MemoryIndex): SearchEngine {
  return {
    search({ query, kind, limit }) {
      const tokens = tokenizeQuery(query);
      const scores = scoreQuery(index, tokens);
      for (const [id, doc] of index.docs.entries()) {
        if (doc.kind === "class" && tokens.includes(doc.name.toLowerCase())) {
          scores.set(id, (scores.get(id) || 0) + 2.0);
        }
        // Slight boost when any query token matches a tokenized part of the class name (e.g., 'HTTP' in 'HTTPRequest').
        if (doc.kind === "class") {
          const nameTokens = new Set(tokenizeName(doc.name));
          let matched = false;
          for (const t of tokens) {
            if (nameTokens.has(t)) {
              matched = true;
              break;
            }
          }
          if (matched) scores.set(id, (scores.get(id) || 0) + 0.5);
        }
      }
      const resultsRaw = Array.from(scores.entries()).map(([docId, score]: [number, number]) => {
        const d = index.docs.get(docId);
        if (!d) return null;
        return {
          uri: toUri(d),
          name: d.kind === "class" ? d.name : `${d.className}.${d.name}`,
          kind: d.kind,
          score,
          snippet: d.brief || d.description || "",
        } as {
          uri: string;
          name: string;
          kind: string;
          score: number;
          snippet?: string;
        };
      });
      let results = resultsRaw.filter((r): r is NonNullable<typeof r> => r !== null);
      if (kind) results = results.filter((r) => r.kind === kind);
      results.sort((a, b) => b.score - a.score);
      if (typeof limit === "number") results = results.slice(0, Math.max(0, limit));
      return results;
    },
  };
}

function tokenizeQuery(q: string): string[] {
  const words = String(q || "")
    .trim()
    .split(/\s+/);
  const toks: string[] = [];
  for (const w of words) toks.push(...tokenizeName(w));
  return toks.map((t) => t.toLowerCase());
}

function toUri(d: { kind: string; name: string; className?: string }): string {
  if (d.kind === "class") return `godot://class/${d.name}`;
  return `godot://symbol/${d.className}/${d.kind}/${d.name}`;
}
