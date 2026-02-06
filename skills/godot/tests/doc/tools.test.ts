import { describe, it } from 'vitest';
import assert from 'node:assert';
import path from 'node:path';

describe('GodotTools adapter', () => {
  it('search returns [] when no hits and validates inputs', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const { createGodotTools } = await import('../../src/doc/adapters/godotTools');
    const classes = await parseAll(path.join('tests','fixtures','godot-docs','fixtures'));
    const index = buildIndex(classes);
    const tools = createGodotTools(classes, index);
    const r = await tools.search({ query: 'nonexistent symbol' });
    assert.deepStrictEqual(r, []);
    let err=null; try { await tools.getClass({}); } catch(e) { err=e; }
    assert.ok(err && err.code==='INVALID_ARGUMENT');
    err=null; try { await tools.getSymbol({}); } catch(e) { err=e; }
    assert.ok(err && err.code==='INVALID_ARGUMENT');
  });
});
