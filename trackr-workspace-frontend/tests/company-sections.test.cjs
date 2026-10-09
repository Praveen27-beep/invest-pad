const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const filename = path.resolve(__dirname, '../lib/company-sections.ts');
const mod = new Module(filename, module);
mod.filename = filename;
mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, filename);
const { companySections, RESEARCH_SECTIONS } = mod.exports;

test('coverage follows canonical company identity, not the display title', () => {
  assert.deepEqual(companySections({ isin: 'INE191H01014', name: 'PVR INOX Limited' }), RESEARCH_SECTIONS);
  assert.ok(!companySections({ symbol: 'TCS' }).includes('Capex Tracker'));
});
test('an internet company may have capex coverage; no blanket sector ban', () => {
  assert.ok(companySections({ symbol: 'ETERNAL' }).includes('Capex Tracker'));
});
test('explicit coverage can change any research heading and always retains Overview', () => {
  assert.deepEqual(companySections({ research_sections: ['Financials', 'Research Report'] }), ['Overview', 'Financials', 'Research Report']);
  assert.deepEqual(companySections({ isin: 'INE191H01014', research_sections: [] }), ['Overview']);
});
test('unregistered companies retain core research without assuming specialised coverage', () => {
  const sections = companySections({ name: 'An unregistered company' });
  assert.ok(sections.includes('Financials'));
  assert.ok(sections.includes('Forensics'));
  assert.ok(!sections.includes('Capex Tracker'));
});
