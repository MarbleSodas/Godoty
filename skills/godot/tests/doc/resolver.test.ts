import { describe, it } from 'vitest';
import assert from 'node:assert';
import path from 'node:path';

describe('SymbolResolver getClass/getSymbol/list', () => {
  it('returns class doc and normalizes sections', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const { createSymbolResolver } = await import('../../src/doc/resolver/symbolResolver');
    const classes = await parseAll(path.join('tests','fixtures','godot-docs','fixtures'));
    const index = buildIndex(classes);
    const r = createSymbolResolver(classes, index);
    const c = r.getClass('Vector2');
    assert.ok(Array.isArray(c.constants) && c.constants.length === 0);
  });

  it('throws NOT_FOUND with suggestions for missing class', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const { createSymbolResolver } = await import('../../src/doc/resolver/symbolResolver');
    const classes = await parseAll(path.join('tests','fixtures','godot-docs','fixtures'));
    const index = buildIndex(classes);
    const r = createSymbolResolver(classes, index);
    let err=null; try { r.getClass('Nod'); } catch (e) { err=e; }
    assert.ok(err && err.code==='NOT_FOUND' && Array.isArray(err.suggestions));
  });

  it('resolves method and validates qname format', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const { createSymbolResolver } = await import('../../src/doc/resolver/symbolResolver');
    const classes = await parseAll(path.join('tests','fixtures','godot-docs','fixtures'));
    const index = buildIndex(classes);
    const r = createSymbolResolver(classes, index);
    const m = r.getSymbol('Node._ready');
    assert.strictEqual(m.kind, 'method');
    let bad=null; try { r.getSymbol('BadFormat'); } catch(e) { bad=e; }
    assert.ok(bad && bad.code==='INVALID_ARGUMENT');
  });

  it('lists classes with prefix and limit', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser.js');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder.js');
    const { createSymbolResolver } = await import('../../src/doc/resolver/symbolResolver.js');
    const classes = await parseAll(path.join('tests','fixtures','godot-docs','fixtures'));
    const index = buildIndex(classes);
    const r = createSymbolResolver(classes, index);
    const list = r.listClasses('B', 1);
    assert.deepStrictEqual(list, ['Button']);
  });
});
