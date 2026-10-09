const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
function load(name) {
  const filename = path.resolve(__dirname, '../lib/' + name + '.ts');
  const mod = new Module(filename, module);
  mod.filename = filename;
  mod.paths = Module._nodeModulePaths(path.dirname(filename));
  mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText, filename);
  return mod.exports;
}
const { auditCoverage, reportOutline } = load('company-research-method');
const { reportSources, evidenceRequirements, businessReport, commitmentHistory, standaloneChecks } = load('pvr-company-report');
test('pasted text and located links cannot satisfy a reviewed-source requirement', () => {
  const requirement = [{label:'Call', role:'CALL', period:'Q1 FY27'}];
  const source = reportSources.find(s => s.id === 'q127');
  for (const status of ['USER_SUPPLIED', 'LOCATED', 'MISSING']) assert.equal(auditCoverage([{...source,status}], requirement)[0].complete, false);
  for (const key of ['url', 'published', 'eventDate']) assert.equal(auditCoverage([{...source,[key]:null}], requirement)[0].complete, false);
  assert.equal(auditCoverage([{...source,period:'Q4 FY26'}],requirement)[0].complete,false);
});
test('coverage preserves the website gap while accounting for annual, four calls and industry', () => {
  const audit = auditCoverage(reportSources,evidenceRequirements);
  assert.equal(audit.filter(r=>r.complete).length,6);
  assert.deepEqual(audit.filter(r=>!r.complete).map(r=>r.role),['WEBSITE']);
});
test('every chapter and reference resolves; revisions retain their earlier evidence', () => {
  assert.deepEqual(businessReport.map(c=>c.id),reportOutline.map(c=>c.id));
  const ids = new Set(reportSources.map(s=>s.id));
  for (const c of businessReport) for(const p of c.paragraphs) for(const ref of p.citations) assert.ok(ids.has(ref.source));
  for (const event of commitmentHistory) assert.ok(ids.has(event.source));
  assert.deepEqual(commitmentHistory.map(e=>e.date), [...commitmentHistory.map(e=>e.date)].sort());
  assert.ok(commitmentHistory.some(e=>e.fact.includes('150')));
  assert.ok(commitmentHistory.some(e=>e.fact.includes('120')));
  assert.ok(commitmentHistory.some(e=>e.fact.includes('90–100')));
});
test('standalone forensic ratios and unit conversion reconcile separately', () => {
  assert.deepEqual(standaloneChecks,{intangibleEquityPercent:'79.6',otherIncomePbtPercent:'53.1',currentLiabilityGap:'1413.8',titleCarryingValue:'341.6'});
});
