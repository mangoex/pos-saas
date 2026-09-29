import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';

const require = createRequire(import.meta.url), ts = require('typescript');
const source=readFileSync('apps/admin-web/src/features/mobile-admin/MobileCashShiftTab.tsx','utf8');
const start=source.indexOf('const handleCreateMovement =');
const end=source.indexOf('const handleCloseShift =',start);
assert.ok(start>=0 && end>start);
const compiled=ts.transpileModule(`${source.slice(start,end)}; exports.run=handleCreateMovement;`,{
  compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS},
}).outputText;
async function run(evidence) {
  const exports={}, requests=[], errors=[];
  vm.runInNewContext(compiled, {exports,movementAmount:'25.00',movementConcept:'Retiro autorizado',
    movementEvidence:evidence,movementType:'withdrawal',branchId:'branch-a',registerId:'register-a',
    setError:value=>errors.push(value),setMovementSubmitting:()=>{},
    fetchApi:async(path,options)=>{requests.push(JSON.parse(options.body));},
    commandKeys:{current:{get:()=> 'stable-test-key',clear:()=>{}}},
    setIsMovementModalOpen:()=>{},setMovementAmount:()=>{},setMovementEvidence:()=>{},
    setNotice:()=>{},loadShift:()=>{},ApiError:Error,
  });
  await exports.run({preventDefault:()=>{}});
  return {requests,errors};
}
test('cash movement never fabricates an evidence reference', async()=>{
  for(const blank of ['', '   ']) {
    const result=await run(blank);
    assert.equal(result.requests.length,0,'Empty evidence must stop before POST');
    assert.ok(result.errors.some(value=>typeof value==='string' && /evidencia|comprobante/i.test(value)));
  }
  const valid=await run('  Vale #12  ');
  assert.equal(valid.requests.length,1);
  assert.deepEqual(valid.requests[0].evidence_refs,['Vale #12']);
});
