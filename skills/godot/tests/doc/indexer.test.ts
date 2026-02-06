import { describe, it } from 'vitest';
import assert from 'node:assert';
import path from 'node:path';

describe('IndexBuilder tokenization and build', () => {
  it('tokenizes class and symbol names including Camera3D variants', async () => {
    const { buildIndex, tokenizeName } = await import('../../src/doc/indexer/indexBuilder');
    assert.deepStrictEqual(tokenizeName('Camera3D'), ['camera','3d','camera3d']);
    const classes = [
      { name: 'Camera3D', brief: '3D camera', description: 'A camera', methods: [], properties: [], signals: [], constants: [] },
      { name: 'Node', brief: 'Node', description: 'Base', methods: [{ name: '_ready', arguments: [], description: 'ready', returnType: 'void' }], properties: [], signals: [], constants: [] }
    ];
    const idx = buildIndex(classes);
    assert.ok(idx.stats.totalDocs >= 2);
    assert.ok(idx.stats.avgDocLen > 0);
  });

  it('tokenizes uppercase acronym + word boundaries and digits', async () => {
    const { tokenizeName } = await import('../../src/doc/indexer/indexBuilder');
    assert.deepStrictEqual(tokenizeName('HTTPRequest'), ['http','request','httprequest']);
    assert.deepStrictEqual(tokenizeName('XRInterface'), ['xr','interface','xrinterface']);
    assert.deepStrictEqual(tokenizeName('CPUParticles3D'), ['cpu','particles','3d','cpuparticles3d']);
  });
});

describe('IndexStore persistence', () => {
  it('saves and loads index JSON', async () => {
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const { saveIndex, loadIndex } = await import('../../src/doc/indexer/indexStore');
    const idx = buildIndex([{ name: 'Vector2', brief: '2D vector', description: 'Math', methods: [], properties: [{ name:'x'}], signals: [], constants: [] }]);
    const pathOut = path.join('.cache','godot-index.json');
    await saveIndex(pathOut, idx);
    const loaded = await loadIndex(pathOut);
    assert.ok(loaded && loaded.stats && loaded.stats.totalDocs === idx.stats.totalDocs);
  });
});
