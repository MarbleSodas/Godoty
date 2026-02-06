import { describe, it } from 'vitest';
import assert from 'node:assert';

describe('Server createServer and handlers', () => {
  it('constructs tools and returns INVALID_ARGUMENT on missing params', async () => {
    const { createServer } = await import('../../src/doc/index.ts');
    const { tools } = await createServer({ MCP_STDIO: '0', GODOT_DOC_DIR: './tests/fixtures/godot-docs/fixtures' });
    let err = null; try { await tools.getSymbol({}); } catch (e) { err = e; }
    assert.ok(err && err.code === 'INVALID_ARGUMENT');
  });
});
