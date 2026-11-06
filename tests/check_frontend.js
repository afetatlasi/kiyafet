// Render/interaction contract smoke test. This is not a browser visual test.
'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const fixture=spawnSync(process.env.PYTHON||'python3',['-c',`
import sys,json
sys.path.insert(0,'tests')
from test_system import ApplicationTests
ApplicationTests.setUpClass()
f=ApplicationTests();f.setUp()
r=f.request();f.to_hq(r);f.stock(0);f.action('hq',r,'approve',quantity=2)
f.assignment()
print(json.dumps({k:f.store.bootstrap(v) for k,v in f.actors.items()},ensure_ascii=False))
f.tearDown()
`],{cwd:root,encoding:'utf8'});
assert.equal(fixture.status,0,fixture.stderr);
const fixtures=JSON.parse(fixture.stdout);
const elements=new Map();
function element(){return {innerHTML:'',textContent:'',hidden:false,value:'',dataset:{},style:{},className:'',open:false,showModal(){this.open=true},close(){this.open=false},addEventListener(){}}}
const document={querySelector(s){if(!elements.has(s))elements.set(s,element());return elements.get(s)},querySelectorAll(){return []},addEventListener(){}};
const context=vm.createContext({document,console,setTimeout,clearTimeout,MutationObserver:class{observe(){}},FormData:class{constructor(form){return Object.entries(form.values)}},fetch:()=>new Promise(()=>{})});
vm.runInContext(fs.readFileSync(path.join(root,'static/app.js'),'utf8'),context);
(async()=>{
 for(const [role,fixture] of Object.entries(fixtures)){
  context.fixture=fixture;
  vm.runInContext('db=fixture',context);
  for(const page of ['dashboard','requests','entitlements','people','stock','assignments','shipments','reports','settings']){
   vm.runInContext(`navigate('${page}')`,context);
   assert.ok(elements.get('#main').innerHTML.includes('title-row'),role+' '+page);
   assert.ok(!elements.get('#main').innerHTML.includes('undefined'),role+' '+page+' has missing data');
  }
  vm.runInContext('newRequest()',context);
  assert.ok(elements.get('#modal').innerHTML.includes('data-form="new-request"'));
  vm.runInContext('catalogForm();userForm();requestDetail(db.requests[0]?.id)',context);
 }
 context.fixture=fixtures.person;vm.runInContext('db=fixture; let lastCall; api=async(path,data)=>{lastCall={path,data};return {ok:true}}',context);
 const cases=[
  ['catalog',{name:'Test',category:'KKD',unit:'Adet',minimum:'2',active:'1',supply_type:'SPECIAL',annual_limit:'1',size_key:'Standart'},'/api/catalog'],
  ['kit',{season:'SUMMER'},'/api/annual-kit'],
  ['replacement',{item_id:'1',size:'L',quantity:'1',priority:'NORMAL',reason:'Erken yıpranma',replacement_assignment_id:'1'},'/api/requests'],
  ['workflow',{allow_local_issue:'true',allow_partial_allocation:'false',require_serial:'true'},'/api/workflow']
 ];
 for(const [kind,values,route] of cases){context.formMock={dataset:{form:kind},values};await vm.runInContext('submit(formMock)',context);const called=vm.runInContext('lastCall',context);assert.equal(called.path,route);if('quantity' in values)assert.equal(typeof called.data.quantity,'number');if(kind==='workflow')assert.equal(typeof called.data.require_serial,'boolean')}
 console.log('PASS: scoped pages render for 8 accounts; catalog, kit, renewal and workflow form contracts passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
