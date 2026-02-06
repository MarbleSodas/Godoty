import { describe, it } from 'vitest';
import assert from 'node:assert';

describe('Env defaults and validation', () => {
  it('applies safe defaults when env missing', async () => {
    const { loadConfig } = await import('../../src/doc/env.js');
    const cfg = loadConfig({});
    assert.strictEqual(cfg.GODOT_DOC_DIR, './doc');
    assert.strictEqual(cfg.GODOT_INDEX_PATH, './.cache/godot-index.json');
    assert.strictEqual(cfg.MCP_SERVER_LOG, 'info');
    assert.strictEqual(cfg.MCP_STDIO, '1');
  });

  it('accepts explicit env vars', async () => {
    const { loadConfig } = await import('../../src/doc/env.js');
    const cfg = loadConfig({
      GODOT_DOC_DIR: './X',
      GODOT_INDEX_PATH: './Y/index.json',
      MCP_SERVER_LOG: 'debug',
      MCP_STDIO: '0'
    });
    assert.strictEqual(cfg.GODOT_DOC_DIR, './X');
    assert.strictEqual(cfg.GODOT_INDEX_PATH, './Y/index.json');
    assert.strictEqual(cfg.MCP_SERVER_LOG, 'debug');
    assert.strictEqual(cfg.MCP_STDIO, '0');
  });

  it('validates Node version check helper', async () => {
    const { isNodeVersionOk } = await import('../../src/doc/env.js');
    assert.strictEqual(isNodeVersionOk('20.0.0'), true);
    assert.strictEqual(isNodeVersionOk('19.9.0'), false);
    assert.strictEqual(isNodeVersionOk('18.19.0'), false);
  });
});

describe('Config validation for doc dir and classes', () => {
  it('fails when classes directory missing', async () => {
    const { validateConfig } = await import('../../src/doc/env.js');
    const bad = { GODOT_DOC_DIR: './does-not-exist', GODOT_INDEX_PATH: './.cache/godot-index.json' };
    let err = null;
    try { validateConfig(bad); } catch (e) { err = e; }
    assert.ok(err && /Invalid GODOT_DOC_DIR/.test(String(err.message)));
  });

  it('passes for repo doc directory', async () => {
    const { loadConfig, validateConfig } = await import('../../src/doc/env.js');
    const cfg = loadConfig({ GODOT_DOC_DIR: './tests/fixtures/godot-docs/fixtures' });
    validateConfig(cfg);
  });
});
