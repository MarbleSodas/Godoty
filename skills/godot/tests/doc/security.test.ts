import { describe, it } from 'vitest';
import assert from 'node:assert';
import path from 'node:path';

describe('Security FS Guard', () => {
  it('allows paths within base directory and rejects escapes', async () => {
    const { withinDir, assertWithinDir, allowIndexPath } = await import('../../src/doc/security/fsGuard.js');
    const base = path.join('.', 'doc');
    const ok = path.join('.', 'doc', 'classes', 'Any.xml');
    assert.strictEqual(withinDir(base, ok), true);
    let err=null; try { assertWithinDir(base, '../etc/passwd'); } catch(e) { err=e; }
    assert.ok(err);
    assert.strictEqual(allowIndexPath('./.cache/godot-index.json', './.cache/godot-index.json'), true);
  });
});
