import { promises as fsp } from "node:fs";
import path from "node:path";
import { XMLParser } from "fast-xml-parser";
import type {
  GodotClassDoc,
  GodotConstant,
  GodotMethod,
  GodotProperty,
  GodotSignal,
} from "../types.js";

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: "",
  trimValues: true,
  allowBooleanAttributes: true,
});

export async function parseAll(rootDir: string): Promise<GodotClassDoc[]> {
  const classesDir = path.join(rootDir, "classes");
  const out: GodotClassDoc[] = [];
  const files = (await fsp.readdir(classesDir)).filter((f) => f.endsWith(".xml"));
  let i = 0;
  for (const f of files) {
    const full = path.join(classesDir, f);
    const xml = await fsp.readFile(full, "utf8");
    try {
      out.push(parseOne(xml));
    } catch (e: unknown) {
      const err = new Error(
        `XML parse error in ${f}: ${e instanceof Error ? e.message : String(e)}`,
      );
      throw err;
    }
    // Periodically yield to keep the event loop responsive for stdio traffic
    if (++i % 25 === 0) {
      await new Promise<void>((res) => setImmediate(res));
    }
  }
  return out;
}

export function parseOne(xml: string): GodotClassDoc {
  type Xml = Record<string, unknown>;
  const j = parser.parse(xml) as unknown as { class?: Xml };
  const root = j.class as Xml | undefined;
  if (!root || typeof root !== "object") throw new Error("Missing <class>");
  const get = <T = unknown>(o: Xml | undefined, key: string): T | undefined =>
    o?.[key] as T | undefined;
  const nameVal = get<string>(root, "name");
  if (!nameVal) throw new Error("Missing class name");
  const name: string = nameVal;
  const inherits: string | undefined = get<string>(root, "inherits");
  const brief: string | undefined = get<string>(root, "brief_description");
  const description: string | undefined = get<string>(root, "description");

  const methods: GodotMethod[] = [];
  const methodsList = asArray<Xml>(
    get<Xml | Xml[] | undefined>(get<Xml>(root, "methods"), "method"),
  );
  for (const m of methodsList) {
    const args = asArray<Xml>(
      get<Xml | Xml[] | undefined>(get<Xml>(m, "arguments"), "argument"),
    ).map((a) => ({
      name: get<string>(a, "name") as string,
      type: get<string>(a, "type"),
      default: get<string>(a, "default"),
    }));
    const qualifiers = asArray<unknown>(
      get<unknown | unknown[] | undefined>(get<Xml>(m, "qualifiers"), "qualifier"),
    ).map((q) => String(q));
    methods.push({
      name: get<string>(m, "name") as string,
      returnType: get<string>(get<Xml>(m, "return"), "type"),
      arguments: args,
      description: get<string>(m, "description"),
      qualifiers,
    });
  }

  const properties: GodotProperty[] = [];
  const membersList = asArray<Xml>(
    (get<Xml | Xml[] | undefined>(get<Xml>(root, "members"), "member") ??
      get<Xml | Xml[] | undefined>(get<Xml>(root, "properties"), "member")) as
      | Xml
      | Xml[]
      | undefined,
  );
  for (const p of membersList) {
    properties.push({
      name: get<string>(p, "name") as string,
      type: get<string>(p, "type"),
      default: get<string>(p, "default"),
      description: get<string>(p, "description"),
    });
  }

  const signals: GodotSignal[] = [];
  const signalsList = asArray<Xml>(
    get<Xml | Xml[] | undefined>(get<Xml>(root, "signals"), "signal"),
  );
  for (const s of signalsList) {
    const args = asArray<Xml>(
      get<Xml | Xml[] | undefined>(get<Xml>(s, "arguments"), "argument"),
    ).map((a) => ({ name: get<string>(a, "name") as string, type: get<string>(a, "type") }));
    signals.push({
      name: get<string>(s, "name") as string,
      arguments: args,
      description: get<string>(s, "description"),
    });
  }

  const constants: GodotConstant[] = [];
  const constsList = asArray<Xml>(
    get<Xml | Xml[] | undefined>(get<Xml>(root, "constants"), "constant"),
  );
  for (const c of constsList) {
    constants.push({
      name: get<string>(c, "name") as string,
      value: get<string>(c, "value"),
      description: get<string>(c, "description"),
    });
  }

  return { name, inherits, brief, description, methods, properties, signals, constants };
}

function asArray<T>(x: T | T[] | undefined): T[] {
  return x === undefined ? [] : Array.isArray(x) ? x : [x];
}
