import { describe, it } from 'vitest';
import assert from 'node:assert';

describe('Logger levels', () => {
  it('suppresses debug when level is info', async () => {
    const { createLogger } = await import('../../src/doc/logger.ts');
    const calls = { debug:0, info:0, warn:0, error:0 };
    const orig = { debug: console.debug, info: console.info, warn: console.warn, error: console.error };
    try {
      console.debug = () => { calls.debug++; };
      console.info = () => { calls.info++; };
      console.warn = () => { calls.warn++; };
      console.error = () => { calls.error++; };
      const log = createLogger('info');
      log.debug('hidden');
      log.info('shown');
      log.warn('warn');
      log.error('err');
    } finally {
      console.debug = orig.debug; console.info = orig.info; console.warn = orig.warn; console.error = orig.error;
    }
    assert.strictEqual(calls.debug, 0);
    assert.strictEqual(calls.info, 1);
    assert.strictEqual(calls.warn, 1);
    assert.strictEqual(calls.error, 1);
  });

  it('emits debug when level is debug', async () => {
    const { createLogger } = await import('../../src/doc/logger.ts');
    let debugCalls = 0;
    const origDebug = console.debug;
    try {
      console.debug = () => { debugCalls++; };
      const log = createLogger('debug');
      log.debug('visible');
    } finally {
      console.debug = origDebug;
    }
    assert.strictEqual(debugCalls, 1);
  });
});
