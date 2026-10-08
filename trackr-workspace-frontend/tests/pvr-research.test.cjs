const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
// Use the repo's TypeScript compiler; no second test framework or production build needed.
const filename = path.resolve(__dirname, '../lib/pvr-research.ts');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true } });
const mod = new Module(filename, module);
mod.filename = filename;
mod.paths = Module._nodeModulePaths(path.dirname(filename));
mod._compile(compiled.outputText, filename);
const { projectScenario, initialScenario, financials, calculations, crore, percent, growth } = mod.exports;
const Decimal = require('decimal.js-light');

test('source units and percent scaling do not introduce a 10x or 100x error', () => {
  assert.equal(crore('67426'), '6742.60');
  assert.equal(percent('9680', '67426'), '14.36');
  assert.equal(percent('22789', '68297'), '33.37');
  assert.equal(growth('2306', '-1360'), null);
  assert.equal(percent('1', '0'), null);
});
test('both filed P&L bases reconcile independently', () => {
  for (const basis of ['reported','adjusted']) for (const year of [0,1]) {
    const values = Object.fromEntries(financials.map(r => [r.label, new Decimal(r[basis][year])]));
    const v = name => values[name];
    assert(v('EBITDA before exceptional items').minus(v('Depreciation & amortisation')).eq(v('EBIT')));
    assert(v('EBIT').minus(v('Finance costs')).minus(v('Joint venture loss')).eq(v('PBT before exceptional items')));
    assert(v('PBT before exceptional items').minus(v('Exceptional charge')).eq(v('Profit before tax')));
    assert(v('Profit before tax').minus(v('Tax expense / (credit)')).eq(v('PAT · continuing operations')));
    assert(v('PAT · continuing operations').plus(v('PAT · discontinued operations')).eq(v('Total PAT')));
  }
});
test('lease and disposal bridges are explicitly different calculations', () => {
  assert.equal(calculations.leaseInclusiveNetDebt, '6182.40');
  assert.equal(calculations.netDebtReduction, '790.30');
  assert.equal(calculations.fcfExDisposal, '568.00');
  assert.equal(calculations.discontinuedShare, '47.09');
});
test('scenario uses decimal values and never adds other income twice', () => {
  const r = projectScenario({...initialScenario,growth:'0',margin:'10',depreciation:'100',interest:'10',tax:'25',multiple:'8',netDebt:'100'});
  assert.equal(r.rows[0].income, '6742.60');
  assert.equal(r.rows[0].ebitda, '674.26');
  assert.equal(r.rows[0].pbt, '563.76');
  assert.equal(r.rows[0].tax, '140.94');
  assert.equal(r.rows[0].pat, '422.82');
  assert.equal(r.enterpriseValue, '5394.08');
  assert.equal(r.equityValue, '5294.08');
});
test('income compounds and net cash increases the equity bridge', () => {
  const r = projectScenario({...initialScenario,growth:'10',netDebt:'-100'});
  assert.equal(r.rows[2].income, '8974.40');
  assert(new Decimal(r.equityValue).eq(new Decimal(r.enterpriseValue).plus(100)));
});
test('invalid, blank and unbounded assumptions produce an error, never a stale value', () => {
  for (const value of ['', '-', 'NaN', 'Infinity', '1e1000', '101', '-101']) assert('error' in projectScenario({...initialScenario,growth:value}));
  assert('error' in projectScenario({...initialScenario,margin:'-1'}));
});
test('loss scenario does not invent a tax credit or clamp a negative equity bridge', () => {
  const r = projectScenario({...initialScenario,growth:'-100',netDebt:'100'});
  assert.equal(r.rows[0].income, '0.00');
  assert.equal(r.rows[0].tax, '0.00');
  assert(new Decimal(r.rows[0].pat).lt(0));
  assert.equal(r.equityValue, '-100.00');
});
