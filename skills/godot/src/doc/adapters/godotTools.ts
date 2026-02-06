import { createSymbolResolver } from "../resolver/symbolResolver.js";
import { createSearchEngine } from "../search/searchEngine.js";
import type { AncestryResponse, GodotClassDoc, GodotSymbolDoc, MemoryIndex } from "../types.js";

export interface GodotTools {
  search(input: {
    query: string;
    kind?: "class" | "method" | "property" | "signal" | "constant";
    limit?: number;
  }): Promise<Array<{ uri: string; name: string; kind: string; score: number; snippet?: string }>>;
  getClass(input: { name: string; includeAncestors?: boolean; maxDepth?: number }): Promise<GodotClassDoc | AncestryResponse>;
  getSymbol(input: { qname: string }): Promise<GodotSymbolDoc>;
  listClasses(input: { prefix?: string; limit?: number }): Promise<string[]>;
}

export function createGodotTools(
  classes: GodotClassDoc[],
  index: MemoryIndex,
  logger?: { debug?: (msg: string, meta?: Record<string, unknown>) => void },
): GodotTools {
  const search = createSearchEngine(index);
  const resolver = createSymbolResolver(classes);
  return {
    async search(input) {
      const { query, kind, limit } = input;
      const q = String(query ?? "").trim();
      if (!q) return [];
      logger?.debug?.("search", { query: q, kind, limit });
      return search.search({ query: q, kind, limit });
    },
    async getClass(input) {
      if (!input || !input.name) {
        const err = new Error("name is required") as Error & { code?: string };
        err.code = "INVALID_ARGUMENT";
        throw err;
      }
      const name = input.name;
      const includeAncestors = Boolean(input.includeAncestors);
      const maxDepth = typeof input.maxDepth === "number" ? input.maxDepth : undefined;
      if (includeAncestors) {
        logger?.debug?.("getClass(includeAncestors)", { name, maxDepth });
        return resolver.getClassChain(name, maxDepth && maxDepth > 0 ? maxDepth : undefined);
      }
      return resolver.getClass(name);
    },
    async getSymbol(input) {
      if (!input || !input.qname) {
        const err = new Error("qname is required") as Error & { code?: string };
        err.code = "INVALID_ARGUMENT";
        throw err;
      }
      return resolver.getSymbol(input.qname);
    },
    async listClasses(input) {
      const prefix = input?.prefix;
      const limit = input?.limit;
      return resolver.listClasses(prefix, limit);
    },
  };
}
