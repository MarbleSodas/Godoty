import { describe, it } from 'vitest';
import assert from 'node:assert';

describe('SymbolResolver ancestry retrieval', () => {
  it('returns inheritanceChain and classes in order', async () => {
    const { createSymbolResolver } = await import('../../src/doc/resolver/symbolResolver');
    const classes = [
      { name: 'Object', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Node', inherits: 'Object', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Control', inherits: 'Node', methods: [], properties: [], signals: [], constants: [] },
      { name: 'BaseButton', inherits: 'Control', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Button', inherits: 'BaseButton', methods: [], properties: [], signals: [], constants: [] },
    ];
    const r = createSymbolResolver(classes);
    const chain = r.getClassChain('Button');
    assert.deepStrictEqual(chain.inheritanceChain.slice(0, 3), ['Button', 'BaseButton', 'Control']);
    assert.strictEqual(chain.classes[0]?.name, 'Button');
    assert.strictEqual(chain.classes[1]?.name, 'BaseButton');
  });

  it('honors maxDepth and reports missing parents', async () => {
    const { createSymbolResolver } = await import('../../src/doc/resolver/symbolResolver');
    const classes = [
      { name: 'Object', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Node', inherits: 'Object', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Widget', inherits: 'MissingBase', methods: [], properties: [], signals: [], constants: [] },
    ];
    const r = createSymbolResolver(classes);
    const chainLimited = r.getClassChain('Node', 1);
    assert.deepStrictEqual(chainLimited.inheritanceChain, ['Node', 'Object']);
    const chainMissing = r.getClassChain('Widget');
    assert.ok(chainMissing.inheritanceChain.includes('MissingBase'));
    assert.ok(Array.isArray(chainMissing.warnings) && chainMissing.warnings.length >= 1);
  });
});

