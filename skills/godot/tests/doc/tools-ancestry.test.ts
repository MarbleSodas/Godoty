import { describe, it } from 'vitest';
import assert from 'node:assert';

describe('GodotTools getClass with includeAncestors', () => {
  it('returns combined ancestry response when requested', async () => {
    const { createGodotTools } = await import('../../src/doc/adapters/godotTools');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const classes = [
      { name: 'Object', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Node', inherits: 'Object', methods: [], properties: [], signals: [], constants: [] },
      { name: 'BaseButton', inherits: 'Node', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Button', inherits: 'BaseButton', methods: [], properties: [], signals: [], constants: [] },
    ];
    const index = buildIndex(classes as any);
    const tools = createGodotTools(classes as any, index as any);
    const res = await tools.getClass({ name: 'Button', includeAncestors: true });
    const payload = res as any;
    assert.ok(Array.isArray(payload.inheritanceChain));
    assert.strictEqual(payload.inheritanceChain[0], 'Button');
    assert.strictEqual(payload.classes[1].name, 'BaseButton');
  });

  it('returns single class doc by default (backward compatible)', async () => {
    const { createGodotTools } = await import('../../src/doc/adapters/godotTools');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const classes = [
      { name: 'Object', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Node', inherits: 'Object', methods: [], properties: [], signals: [], constants: [] },
    ];
    const index = buildIndex(classes as any);
    const tools = createGodotTools(classes as any, index as any);
    const single = await tools.getClass({ name: 'Node' });
    assert.strictEqual((single as any).name, 'Node');
  });
});

