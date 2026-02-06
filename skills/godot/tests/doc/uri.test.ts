import { describe, it } from 'vitest';
import assert from 'node:assert';

describe('URI formatting', () => {
  it('builds search uri with q and kind', async () => {
    const { formatSearchUri } = await import('../../src/doc/uri.js');
    const u = formatSearchUri('Node', 'class');
    assert.strictEqual(u, 'godot://search?q=Node&kind=class');
  });
});
