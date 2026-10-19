import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const read=(path)=>fs.readFileSync(new URL(path,import.meta.url),'utf8');
test('API never posts raw coordinates or constructed game actions',()=>{
  const api=read('../src/lib/api.ts');
  assert.match(api,/action_id: actionId, expected_revision: revision/);
  assert.doesNotMatch(api,/source_hex_id:|target_hex_id:|unit_type:/);
});
test('preview fixture not a fallback after API failure',()=>{
  const app=read('../src/App.tsx');
  assert.match(app,/preview\?previewView:null/);
  assert.match(app,/if\(preview\|\|busy/);
  assert.doesNotMatch(app,/catch\([^\n]*\)\s*\{\s*setView\(previewView\)/);
});
test('API client uses cookies, revision conflict handling, no-store',()=>{
  const api=read('../src/lib/api.ts'),app=read('../src/App.tsx');
  assert.match(api,/credentials: 'include'/);
  assert.match(api,/cache: 'no-store'/);
  assert.match(app,/status===409/);
  assert.match(app,/lastAppliedRevision/);
});
