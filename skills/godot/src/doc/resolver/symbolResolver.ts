import type { GodotClassDoc, GodotSymbolDoc, AncestryResponse } from "../types.js";

function normalizeSections(c: GodotClassDoc): GodotClassDoc {
  return {
    ...c,
    methods: Array.isArray(c.methods) ? c.methods : [],
    properties: Array.isArray(c.properties) ? c.properties : [],
    signals: Array.isArray(c.signals) ? c.signals : [],
    constants: Array.isArray(c.constants) ? c.constants : [],
  };
}

export function createSymbolResolver(classes: GodotClassDoc[]) {
  const byName = new Map<string, GodotClassDoc>(classes.map((c) => [c.name, normalizeSections(c)]));
  const classNames = classes.map((c) => c.name).sort();

  function didYouMean(name: string): string[] {
    const lower = name.toLowerCase();
    const candidates = classNames
      .map((n) => ({ n, d: distance(lower, n.toLowerCase()) }))
      .sort((a, b) => a.d - b.d)
      .slice(0, 5)
      .map((x) => x.n);
    return candidates;
  }

  return {
    getClassChain(name: string, maxDepth?: number): AncestryResponse {
      const start = byName.get(name);
      const warnings: string[] = [];
      if (!start) {
        const suggestions = didYouMean(name);
        const err = new Error(`Class not found: ${name}`) as Error & {
          code?: string;
          suggestions?: string[];
        };
        err.code = "NOT_FOUND";
        err.suggestions = suggestions;
        throw err;
      }
      const chain: string[] = [];
      const docs: GodotClassDoc[] = [];
      let depth = 0;
      let cur: GodotClassDoc | undefined = start;
      while (cur) {
        chain.push(cur.name);
        docs.push(cur);
        depth++;
        if (typeof maxDepth === "number" && maxDepth > 0 && depth > maxDepth) break;
        const parentName = cur.inherits;
        if (!parentName) break;
        const parent = byName.get(parentName);
        if (!parent) {
          chain.push(parentName);
          warnings.push(`Missing parent doc for '${parentName}'`);
          break;
        }
        cur = parent;
      }
      return warnings.length ? { inheritanceChain: chain, classes: docs, warnings } : { inheritanceChain: chain, classes: docs };
    },
    getClass(name: string): GodotClassDoc {
      const c = byName.get(name);
      if (!c) {
        const suggestions = didYouMean(name);
        const err = new Error(`Class not found: ${name}`) as Error & {
          code?: string;
          suggestions?: string[];
        };
        err.code = "NOT_FOUND";
        err.suggestions = suggestions;
        throw err;
      }
      return c;
    },
    getSymbol(qname: string): GodotSymbolDoc {
      if (!/^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$/.test(qname)) {
        const err = new Error(`Invalid qualified name: ${qname}`) as Error & {
          code?: string;
        };
        err.code = "INVALID_ARGUMENT";
        throw err;
      }
      const [cls, member] = qname.split(".");
      const c = byName.get(cls);
      if (!c) {
        const err = new Error(`Class not found: ${cls}`) as Error & {
          code?: string;
          suggestions?: string[];
        };
        err.code = "NOT_FOUND";
        err.suggestions = didYouMean(cls);
        throw err;
      }
      // Search this class, then traverse base classes via `inherits`.
      const visited = new Set<string>();
      let cur: GodotClassDoc | undefined = c;
      while (cur && !visited.has(cur.name)) {
        visited.add(cur.name);
        const m = (cur.methods || []).find((x) => x.name === member);
        if (m) return { kind: "method", className: cls, ...m } as GodotSymbolDoc;
        const p = (cur.properties || []).find((x) => x.name === member);
        if (p) return { kind: "property", className: cls, ...p } as GodotSymbolDoc;
        const s = (cur.signals || []).find((x) => x.name === member);
        if (s) return { kind: "signal", className: cls, ...s } as GodotSymbolDoc;
        const k = (cur.constants || []).find((x) => x.name === member);
        if (k) return { kind: "constant", className: cls, ...k } as GodotSymbolDoc;
        cur = cur.inherits ? byName.get(cur.inherits) : undefined;
      }
      const err = new Error(`Symbol not found: ${qname}`) as Error & {
        code?: string;
        suggestions?: string[];
      };
      err.code = "NOT_FOUND";
      // Build suggestions from this class and its base classes
      const sugg: string[] = [];
      let cur2: GodotClassDoc | undefined = c;
      const seen = new Set<string>();
      while (cur2 && sugg.length < 5 && !seen.has(cur2.name)) {
        seen.add(cur2.name);
        for (const x of cur2.methods) {
          if (sugg.length >= 5) break;
          sugg.push(`${cls}.${x.name}`);
        }
        for (const x of cur2.properties) {
          if (sugg.length >= 5) break;
          sugg.push(`${cls}.${x.name}`);
        }
        for (const x of cur2.signals) {
          if (sugg.length >= 5) break;
          sugg.push(`${cls}.${x.name}`);
        }
        for (const x of cur2.constants) {
          if (sugg.length >= 5) break;
          sugg.push(`${cls}.${x.name}`);
        }
        cur2 = cur2.inherits ? byName.get(cur2.inherits) : undefined;
      }
      err.suggestions = sugg;
      throw err;
    },
    listClasses(prefix?: string, limit?: number): string[] {
      let list = classNames;
      if (prefix) {
        const pre = prefix.toLowerCase();
        list = list.filter((n) => n.toLowerCase().startsWith(pre));
      }
      if (typeof limit === "number") list = list.slice(0, Math.max(0, limit));
      return list;
    },
  };
}

function distance(a: string, b: string): number {
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i++) dp[i][0] = i;
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  return dp[a.length][b.length];
}
