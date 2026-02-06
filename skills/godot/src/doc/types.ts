export interface GodotMethodArg {
  name: string;
  type?: string;
  default?: string;
}
export interface GodotSignalArg {
  name: string;
  type?: string;
}

export interface GodotMethod {
  name: string;
  returnType?: string;
  arguments: GodotMethodArg[];
  description?: string;
  qualifiers?: string[];
}

export interface GodotProperty {
  name: string;
  type?: string;
  default?: string;
  description?: string;
}

export interface GodotSignal {
  name: string;
  arguments: GodotSignalArg[];
  description?: string;
}

export interface GodotConstant {
  name: string;
  value?: string;
  description?: string;
}

export interface GodotClassDoc {
  name: string;
  inherits?: string;
  category?: string;
  brief?: string;
  description?: string;
  methods: GodotMethod[];
  properties: GodotProperty[];
  signals: GodotSignal[];
  constants: GodotConstant[];
  themeItems?: Record<string, string[]>;
  annotations?: string[];
  since?: string;
}

export type GodotSymbolDoc =
  | ({ kind: "method"; className: string } & GodotMethod)
  | ({ kind: "property"; className: string } & GodotProperty)
  | ({ kind: "signal"; className: string } & GodotSignal)
  | ({ kind: "constant"; className: string } & GodotConstant);

export interface AncestryResponse {
  inheritanceChain: string[];
  classes: GodotClassDoc[];
  warnings?: string[];
}

export interface Posting {
  docId: number;
  tf: number;
}
export interface TermEntry {
  term: string;
  postings: Posting[];
  df: number;
}
export interface DocEntry {
  id: number;
  kind: "class" | "method" | "property" | "signal" | "constant";
  name: string;
  className?: string;
  brief?: string;
  description?: string;
}
export interface MemoryIndex {
  terms: Map<string, TermEntry>;
  docs: Map<number, DocEntry>;
  byQualified: Map<string, number>;
  byClass: Map<string, number[]>;
  docLengths: Map<number, number>;
  stats: { totalDocs: number; avgDocLen: number };
}
