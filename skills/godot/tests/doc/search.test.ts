import { describe, it } from 'vitest';
import assert from 'node:assert';
import path from 'node:path';

describe('SearchEngine', () => {
  it('ranks exact class name highest and supports kind filter and limit', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const { createSearchEngine } = await import('../../src/doc/search/searchEngine');
    const classes = await parseAll(path.join('tests','fixtures','godot-docs','fixtures'));
    const index = buildIndex(classes);
    const se = createSearchEngine(index);
    const r1 = se.search({ query: 'Node' });
    assert.ok(r1[0].name.startsWith('Node'));
    const r2 = se.search({ query: 'pressed', kind: 'signal' });
    assert.ok(r2.find(x => x.name.endsWith('.pressed')));
    const r3 = se.search({ query: 'vector', limit: 1 });
    assert.strictEqual(r3.length, 1);
  });

  it('finds acronym-based classes case-insensitively', async () => {
    const { parseAll } = await import('../../src/doc/parser/xmlParser');
    const { buildIndex } = await import('../../src/doc/indexer/indexBuilder');
    const { createSearchEngine } = await import('../../src/doc/search/searchEngine');
    const classes = await parseAll(path.join('tests','fixtures','godot-docs','fixtures'));
    const index = buildIndex(classes);
    const se = createSearchEngine(index);

    const rHttp = se.search({ query: 'HTTP' });
    if (!rHttp.length) throw new Error('No results for HTTP');
    if (!rHttp[0].name.startsWith('HTTPRequest')) throw new Error('HTTPRequest not ranked first for HTTP');

    const rXr = se.search({ query: 'xr' });
    if (!rXr.find(x => x.name.startsWith('XRInterface'))) throw new Error('XRInterface not found for xr');

    const rCpu = se.search({ query: 'CPU' });
    if (!rCpu.find(x => x.name.startsWith('CPUParticles3D'))) throw new Error('CPUParticles3D not found for CPU');
  });
});
