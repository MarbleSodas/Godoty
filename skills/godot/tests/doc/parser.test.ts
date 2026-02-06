import { describe, it } from 'vitest';
import assert from 'node:assert';
import path from 'node:path';

describe('XML Parser to GodotClassDoc', () => {
  it('parses fixtures and normalizes missing sections to empty arrays', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    const dir = path.join('tests','fixtures','godot-docs','fixtures');
    const classes = await parseAll(dir);
    const names = classes.map(c => c.name);
    // Ensure baseline fixtures are present; others may be added
    for (const must of ['Button','Node','Vector2']) {
      assert.ok(names.includes(must), `missing expected class ${must}`);
    }

    const node = classes.find(c => c.name === 'Node');
    // debug
    // console.log('NODE', node);
    assert.ok(node.brief && node.description);
    assert.ok(Array.isArray(node.methods) && node.methods.length === 1);
    assert.strictEqual(node.methods[0].name, '_ready');
    assert.strictEqual(node.methods[0].returnType, 'void');
    assert.deepStrictEqual(node.methods[0].arguments, [{ name: 'delta', type: 'float', default: '0' }]);
    assert.ok(node.methods[0].description.includes('called when added'));
    assert.ok(Array.isArray(node.properties));
    assert.ok(Array.isArray(node.signals));
    assert.ok(Array.isArray(node.constants));

    const v2 = classes.find(c => c.name === 'Vector2');
    assert.ok(v2);
    const px = v2.properties.find(p => p.name === 'x');
    assert.strictEqual(px.type, 'float');
    assert.strictEqual(v2.constants.length, 0);

    const btn = classes.find(c => c.name === 'Button');
    const sig = btn.signals.find(s => s.name === 'pressed');
    assert.ok(sig && sig.description.includes('emitted when'));
  });
  it('reports filename on parse error', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    let err=null; try { await parseAll('tests/fixtures/godot-docs/fixtures-bad'); } catch(e) { err=e; }
    assert.ok(err && /Broken.xml/.test(String(err.message)));
  });
});
