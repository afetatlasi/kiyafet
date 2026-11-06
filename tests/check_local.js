'use strict';
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),memory=new Map();
let failSave=false;
const storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>{if(failSave)throw Error('quota');memory.set(k,v)}};
function context(extra={}){const c=vm.createContext({localStorage:storage,console,Intl,Date,setTimeout,clearTimeout,...extra});vm.runInContext(fs.readFileSync(path.join(root,'static/local-store.js'),'utf8'),c);return c}
const c=context(),api=c.AFADLocal;const call=(p,d)=>api.api('/api/'+p,d);const select=x=>api.select(x);
const user={full_name:'Test Personeli',registry:'TEST-001',role:'PERSONNEL',province_id:6,unit_id:6,title:'Arama Kurtarma Teknisyeni',specialty:'KBRN',start_date:'2026-01-01',active:1};
(async()=>{
 let d=await call('bootstrap');assert.equal(d.user.role,'ADMIN');assert.equal(d.provinces.length,81);assert.equal(d.requests.length,0);
 await call('users',user);select({role:'PERSONNEL'});await call('sizes',{sizes:{'Üst':'L','Alt':'L','Mont':'XL','Ayakkabı':'43','Eldiven':'9'}});
 await call('annual-kit',{season:'SUMMER'});await call('annual-kit',{season:'WINTER'});d=await call('bootstrap');assert.equal(d.requests.length,7);assert.ok(d.requests.some(r=>r.item.includes('Ayakkabısı')));assert.ok(d.requests.some(r=>r.item.includes('Botu')));
 await assert.rejects(call('annual-kit',{season:'SUMMER'}));assert.equal((await call('bootstrap')).requests.length,7);
 const shoe=d.requests.find(r=>r.item.includes('Ayakkabısı'));
 select({role:'MATERIAL'});await call('stock',{location:6,item_id:shoe.item_id,size:'43',delta:2,note:'Depo giriş belgesi'});await call('request-action',{id:shoe.id,action:'issue',quantity:1,serial:''});
 await assert.rejects(call('request-action',{id:shoe.id,action:'issue',quantity:1,serial:''}));
 select({role:'PERSONNEL'});d=await call('bootstrap');const a=d.assignments[0];await call('assignment-action',{id:a.id,action:'confirm'});
 await call('requests',{item_id:shoe.item_id,size:'43',quantity:1,request_kind:'REPLACEMENT',replacement_assignment_id:a.id,priority:'NORMAL',reason:'Operasyonda erken yıpranma'});
 d=await call('bootstrap');assert.equal(d.incidents.length,1);assert.equal(d.entitlements.find(e=>e.item_id===shoe.item_id).used_or_pending,1);
 await assert.rejects(call('requests',{item_id:shoe.item_id,size:'43',quantity:1,request_kind:'REPLACEMENT',replacement_assignment_id:a.id,priority:'NORMAL',reason:'Tekrar aynı yenileme'}));
 const special=d.catalog.find(i=>i.name==='KBRN Koruyucu Tulum');await call('requests',{item_id:special.id,size:'L',quantity:3,priority:'URGENT',reason:'KBRN görev ekipmanı ihtiyacı'});d=await call('bootstrap');const r=d.requests[0];
 select({role:'MATERIAL'});await call('request-action',{id:r.id,action:'review'});select({role:'DIRECTOR'});await call('batches',{request_ids:[r.id],note:'Toplu malzeme ihtiyacı'});
 select({role:'HQ'});await assert.rejects(call('request-action',{id:r.id,action:'approve',quantity:2}));assert.equal(api.snapshot().requests.find(x=>x.id===r.id).status,'HQ_REVIEW');
 await call('stock',{location:0,item_id:special.id,size:'L',delta:5,note:'Merkez depo giriş belgesi'});await call('request-action',{id:r.id,action:'approve',quantity:2});await call('request-action',{id:r.id,action:'ship',shipment_ref:'SVK-001'});
 select({role:'MATERIAL'});await call('request-action',{id:r.id,action:'receive'});await assert.rejects(call('request-action',{id:r.id,action:'receive'}));await call('request-action',{id:r.id,action:'issue',quantity:2,serial:''});
 d=await call('bootstrap');assert.equal(d.requests.find(x=>x.id===r.id).status,'PARTIAL_COMPLETED');const newAssignment=d.assignments.find(x=>x.request_id===r.id);
 select({role:'PERSONNEL'});await call('assignment-action',{id:newAssignment.id,action:'confirm'});select({role:'MATERIAL'});await call('assignment-action',{id:newAssignment.id,action:'return',note:'Operasyon sonrası iade'});await assert.rejects(call('assignment-action',{id:newAssignment.id,action:'return',note:'Mükerrer iade'}));
 select({role:'ADMIN'});const saved=api.snapshot();const c2=context();assert.equal(c2.AFADLocal.snapshot().requests.length,saved.requests.length);assert.equal(c2.AFADLocal.snapshot().assignments.length,2);
 failSave=true;await assert.rejects(call('stock',{location:6,item_id:special.id,size:'L',delta:10,note:'Depolama hatası denemesi'}));failSave=false;assert.equal(JSON.stringify(api.snapshot()),JSON.stringify(saved));
 await api.restore({size:10,text:async()=>JSON.stringify(saved)});assert.equal(api.snapshot().requests.length,saved.requests.length);
 const corrupt=JSON.parse(JSON.stringify(saved));corrupt.stock[0].quantity=-1;await assert.rejects(api.restore({size:10,text:async()=>JSON.stringify(corrupt)}));
 // The live app must open its dashboard without making any network request.
 const nodes=new Map();function node(){return {innerHTML:'',textContent:'',hidden:false,style:{},dataset:{},open:false,insertAdjacentHTML(position,html){this.innerHTML=position==='afterbegin'?html+this.innerHTML:this.innerHTML+html},addEventListener(){},querySelector(){return node()},querySelectorAll(){return []},close(){this.open=false},showModal(){this.open=true}}}
 const doc={body:{dataset:{localMode:'true'}},querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s)},querySelectorAll(){return []},addEventListener(){}};
 const app=context({document:doc,MutationObserver:class{observe(){}},fetch(){throw Error('No network is allowed in local mode')}});vm.runInContext(fs.readFileSync(path.join(root,'static/app.js'),'utf8'),app);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(nodes.get('#app').hidden,false);assert.equal(nodes.get('#login-view').hidden,true);assert.ok(nodes.get('#main').innerHTML.includes('Şifresiz yerel çalışma'));assert.ok(nodes.get('#main').innerHTML.includes('Genel Bakış'));
 const index=fs.readFileSync(path.join(root,'index.html'),'utf8');assert.ok(index.includes('data-local-mode="true"'));assert.ok(index.indexOf('local-store.js')<index.indexOf('./static/app.js'));
 console.log('PASS: password-free startup, annual kits with shoes, early replacement, KBRN workflow, partial allocation, receipt/return, persistence, backup restore and failed-write rollback.');
})().catch(e=>{console.error(e);process.exitCode=1});
