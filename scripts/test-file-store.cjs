// Pure Node regression tests for the inline file bridge; no browser package needed.
// File System Access permission / write failures are modeled with explicit handles.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const source=fs.readFileSync(path.join(__dirname,'file-store.js'),'utf8');
function fixture(){
  const p=JSON.parse(fs.readFileSync(path.join(root,'progress/plan90.json'),'utf8'));
  p.weeks.forEach(w=>{w.note='';w.tasks.forEach(t=>Object.assign(t,{done:false,note:'',completedOn:null,evidence:[]}));});
  p.deliverables.forEach(t=>Object.assign(t,{done:false,note:'',completedOn:null,evidence:[]}));
  p.checkins=[];p.dailyLogs={};p.overrides=[];p.history=[];p.meta.revision=1;
  p.stats={totalTasks:p.weeks.reduce((n,w)=>n+w.tasks.length,0),doneTasks:0,pct:0,delivDone:0,delivTotal:p.deliverables.length};
  return p;
}
function setup({blocked=false,cache={}}={}){
  const nodes={sourceStatus:{},connBtn:{},restoreBtn:{}}, memory=new Map(Object.entries(cache));
  const ctx=vm.createContext({console,Date,Intl,URL,Blob,setTimeout,clearTimeout,confirm:()=>true,location:{reload(){ctx.reloaded=true;}},
    document:{getElementById:id=>nodes[id]||null},window:{},
    localStorage:{getItem(k){if(blocked)throw Error('SecurityError');return memory.get(k)||null;},setItem(k,v){if(blocked)throw Error('QuotaExceeded');memory.set(k,v);}}});
  vm.runInContext(source+'\nglobalThis.api={ProjectFileStore,validatePlan,validateFaults,planStats,projectDayInfo,projectToday,deepCopy,recordEvent,convertLegacy};',ctx);
  const api=ctx.api, data=fixture();
  const store=new api.ProjectFileStore({initial:data,fileHint:'progress/plan90.json',validator:api.validatePlan,
    normalize:p=>p.stats=api.planStats(p),convert:api.convertLegacy,onChange:d=>{ctx.changed=d;},legacyKey:'plan90_v1'});
  return {ctx,api,store,nodes,memory};
}
function handle(data,{failWrite=false,permission='granted'}={}){
  let raw=JSON.stringify(data,null,2)+'\n',writes=0,aborted=0;
  return {name:'plan90.json',get raw(){return raw;},set raw(v){raw=v;},get writes(){return writes;},get aborted(){return aborted;},
    async queryPermission(){return permission;},async requestPermission(){return permission;},
    async getFile(){return {async text(){return raw;}};},
    async createWritable(){let buffer;return {async write(v){if(failWrite)throw Error('write failed');buffer=v;},
      async close(){raw=buffer;writes++;},async abort(){aborted++;}};}};
}
const testCases=[];
function test(name,fn){testCases.push([name,fn]);}
function first(p){return p.weeks.flatMap(w=>w.tasks).find(t=>t.id==='1-0');}
async function connect(env,h){env.ctx.window.showOpenFilePicker=async()=>[h];assert.equal(await env.store.connect(),true);}

test('snapshot is readable but cannot silently write',async()=>{
  const e=setup();assert.equal(await e.store.update(p=>first(p).done=true),false);assert.equal(first(e.store.data).done,false);
  assert.match(e.nodes.sourceStatus.textContent,/只读快照/);
});
test('stale cache never overrides embedded authoritative snapshot',async()=>{
  const e=setup({cache:{plan90_v1:JSON.stringify({done:{'1-0':true}})}});
  assert.equal(first(e.store.data).done,false);assert.ok(e.store.legacy);
});
test('permission rejected: no connection and no state replacement',async()=>{
  const e=setup(),data=fixture();first(data).done=true;data.stats=e.api.planStats(data);
  const h=handle(data,{permission:'denied'});e.ctx.window.showOpenFilePicker=async()=>[h];
  assert.equal(await e.store.connect(),false);assert.equal(e.store.mode,'snapshot');assert.equal(first(e.store.data).done,false);
});
test('wrong schema rejected before obtaining write target',async()=>{
  const e=setup(),h=handle({schema:'bad'});e.ctx.window.showOpenFilePicker=async()=>[h];
  assert.equal(await e.store.connect(),false);assert.equal(e.store.handle,null);assert.equal(h.writes,0);
});
test('file write preserves task IDs, notes, unknown fields and history',async()=>{
  const e=setup(),data=fixture();data.futureMeta={keep:true};data.weeks[0].note='week note';data._orphans=[{id:'old'}];
  const h=handle(data);await connect(e,h);
  assert.equal(await e.store.update(p=>{first(p).done=true;first(p).completedOn='2026-09-06';first(p).note='task note';e.api.recordEvent(p,'done',{ids:['1-0']});}),true);
  const saved=JSON.parse(h.raw);assert.equal(saved.stats.doneTasks,1);assert.equal(saved.weeks[0].note,'week note');
  assert.equal(first(saved).note,'task note');assert.equal(saved.futureMeta.keep,true);assert.equal(saved._orphans[0].id,'old');assert.equal(saved.history.length,1);
});
test('write failure cannot fall back to cache or claim file success',async()=>{
  const e=setup(),h=handle(fixture(),{failWrite:true});await connect(e,h);const before=h.raw;
  assert.equal(await e.store.update(p=>first(p).done=true),false);assert.equal(h.raw,before);assert.equal(first(e.store.data).done,false);
  assert.equal(h.writes,0);assert.equal(e.memory.size,0);assert.equal(h.aborted,1);assert.match(e.nodes.sourceStatus.textContent,/未写入文件/);
});
test('rapid writes are serialized without lost updates',async()=>{
  const e=setup(),h=handle(fixture());await connect(e,h);
  const results=await Promise.all([e.store.update(p=>{first(p).note='first';}),e.store.update(p=>{first(p).note+=' second';})]);
  assert.equal(results.every(Boolean),true);assert.equal(first(JSON.parse(h.raw)).note,'first second');assert.equal(h.writes,2);
});
test('agent update conflict rejected; reload then merge works',async()=>{
  const e=setup(),h=handle(fixture());await connect(e,h);
  const newer=JSON.parse(h.raw);newer.weeks[0].note='agent update';newer.meta.revision+=1;h.raw=JSON.stringify(newer)+'\n';const before=h.raw;
  assert.equal(await e.store.update(p=>first(p).done=true),false);assert.equal(h.raw,before);assert.equal(h.writes,0);
  assert.match(e.nodes.sourceStatus.textContent,/拒绝覆盖/);await e.store.reload();
  assert.equal(await e.store.update(p=>first(p).done=true),true);assert.equal(JSON.parse(h.raw).weeks[0].note,'agent update');
});
test('invalid import leaves current view and file untouched',async()=>{
  const e=setup(),h=handle(fixture());await connect(e,h);const before=h.raw;
  assert.equal(await e.store.importFile({async text(){return '{broken';}}),false);assert.equal(h.raw,before);assert.equal(e.store.mode,'file');
});
test('valid import becomes draft, never overwrites attached file',async()=>{
  const e=setup(),h=handle(fixture());await connect(e,h);const before=h.raw;
  const imported=fixture();first(imported).done=true;imported.stats=e.api.planStats(imported);
  assert.equal(await e.store.importFile({async text(){return JSON.stringify(imported);}}),true);
  assert.equal(e.store.mode,'draft');assert.equal(e.store.handle,null);assert.equal(h.raw,before);
});
test('no localStorage: snapshot still renders, file mode still saves',async()=>{
  const e=setup({blocked:true});e.store.refresh();assert.match(e.nodes.sourceStatus.textContent,/文件快照/);
  const h=handle(fixture());await connect(e,h);assert.equal(await e.store.update(p=>first(p).done=true),true);assert.equal(h.writes,1);
});
test('no localStorage: draft warns clearly of memory-only changes',async()=>{
  const e=setup({blocked:true});assert.equal(e.store.enableDraft(),true);
  assert.equal(await e.store.update(p=>first(p).done=true),true);assert.match(e.nodes.sourceStatus.textContent,/不能保存缓存/);
  assert.match(e.nodes.sourceStatus.textContent,/未写入项目/);
});
test('date boundaries and night mode match intended calendar',async()=>{
  const e=setup(),p=fixture();
  for(const [ds,n] of [['2026-09-05',-1],['2026-09-06',0],['2026-09-07',1],['2026-10-06',30],['2026-11-05',60],['2026-12-05',90],['2026-12-13',98],['2026-12-14',99]])assert.equal(e.api.projectDayInfo(p,ds).day,n);
  p.overrides=[{start:'2026-10-05',end:'2026-10-10',mode:'night'}];const info=e.api.projectDayInfo(p,'2026-10-06');
  assert.equal(info.actions.length,0);assert.equal(info.budgetMinutes,10);
});
test('malformed booleans and duplicate IDs rejected',async()=>{
  const e=setup(),p=fixture();first(p).done='false';assert.throws(()=>e.api.validatePlan(p));
  const other=fixture();other.weeks[0].tasks[1].id=other.weeks[0].tasks[0].id;assert.throws(()=>e.api.validatePlan(other));
});
test('B2 future dates in full snapshots and legacy backups reject the entire import',async()=>{
  for(const payload of [Object.assign(fixture(),{checkins:['2099-01-01']}),{done:{'1-0':true},notes:{'1-2':'must not partly merge'},checkins:['2099-01-01']}]){
    const e=setup(),h=handle(fixture());await connect(e,h);const raw=h.raw,before=JSON.stringify(e.store.data);
    assert.equal(await e.store.importFile({async text(){return JSON.stringify(payload);}}),false);
    assert.equal(e.store.mode,'file');assert.equal(JSON.stringify(e.store.data),before);assert.equal(h.raw,raw);
  }
});
test('B2 bad incoming completion dates cannot hide behind a newer destination date',async()=>{
  const e=setup(),p=fixture();first(p).done=true;first(p).completedOn='2026-09-06';p.stats=e.api.planStats(p);
  const incoming={schema:'self-evolution/plan90/v1',weeks:[{n:1,tasks:[{id:'1-0',done:true,completedOn:'2099-01-01'}]}]};
  const before=JSON.stringify(p);assert.throws(()=>e.api.convertLegacy(incoming,p));assert.equal(JSON.stringify(p),before);
});
test('B4 invalid schedule and state shapes are consistently rejected',async()=>{
  const changes=[p=>first(p).scheduledDate='2026-09-01',p=>first(p).dueDate='2027-01-01',p=>delete first(p).track,
    p=>first(p).track='toString',p=>first(p).note=null,p=>first(p).evidence=null,p=>first(p).dependsOn=null,
    p=>first(p).completedOn=0,p=>p.checkins=['2026-09-05'],p=>p.dailyLogs={'2099-01-01':{note:'future'}},
    p=>p.overrides=[{start:'2026-09-01',end:'2026-09-06',mode:'night'}]];
  const e=setup();
  for(const change of changes){const p=fixture();change(p);assert.throws(()=>e.api.validatePlan(p),'must reject '+change);}
});
test('B5 notes-only task and orphan notes survive; existing week notes are not overwritten',async()=>{
  const e=setup(),p=fixture();p.weeks[0].note='newer week';
  const input={done:{},notes:{'1':'old week','1-2':'only a note','removed-7':'old orphan'},deliv:{},checkins:[]};
  const result=e.api.convertLegacy(input,p),t=result.weeks.flatMap(w=>w.tasks).find(t=>t.id==='1-2');
  assert.equal(t.note,'only a note');assert.equal(t.done,false);assert.match(result.weeks[0].note,/newer week/);assert.match(result.weeks[0].note,/old week/);
  assert.equal(result._orphans.find(t=>t.id==='removed-7').note,'old orphan');assert.equal(p.weeks[0].note,'newer week');
});
test('B5 repeated legacy merges do not duplicate multiline notes or orphan entries',async()=>{
  const e=setup(),p=fixture();p.weeks[0].note='newer week';
  const input={done:{'1-0':true,'removed-8':true},notes:{'1':'old\nweek','1-0':'old\nnote','removed-8':'orphan'},checkins:[]};
  const once=e.api.convertLegacy(input,p),twice=e.api.convertLegacy(input,once);
  assert.equal(first(once).note,first(twice).note);assert.equal(once.weeks[0].note,twice.weeks[0].note);
  assert.equal(JSON.stringify(once._orphans),JSON.stringify(twice._orphans));
});
test('B5 legacy evidence and known completion dates survive in the draft',async()=>{
  const e=setup(),p=fixture(),incoming={schema:'self-evolution/plan90/v1',weeks:[{n:1,note:'old week',tasks:[
    {id:'1-0',done:true,note:'a note',completedOn:'2026-09-06',evidence:['local-artifact']}]}],checkins:[],dailyLogs:{'2026-09-06':{note:'actual work',minutes:25}}};
  const result=e.api.convertLegacy(incoming,p);assert.equal(first(result).completedOn,'2026-09-06');
  assert.equal(first(result).evidence[0],'local-artifact');assert.equal(result.dailyLogs['2026-09-06'].minutes,25);
});
test('B5 explicit legacy-cache restoration is a draft and preserves note-only records',async()=>{
  const legacy={done:{},notes:{'1-2':'cached note'},checkins:[]},e=setup({cache:{plan90_v1:JSON.stringify(legacy)}});
  assert.equal(e.store.mode,'snapshot');assert.equal(e.store.restoreDraft(),true);assert.equal(e.store.mode,'draft');
  assert.equal(e.store.data.weeks.flatMap(w=>w.tasks).find(t=>t.id==='1-2').note,'cached note');assert.equal(e.store.handle,null);
});
test('B6 overdue release or unaccepted song delivery pauses IPA, not unrelated publication tasks',async()=>{
  const e=setup(),p=fixture();p.weeks.flatMap(w=>w.tasks).forEach(t=>{if(t.track==='sound')t.done=true;});
  const info=()=>e.api.projectDayInfo(p,'2026-10-16').actions.map(a=>a.taskId),before=JSON.stringify(p);
  assert.equal(info().includes('6-5'),false);assert.equal(JSON.stringify(p),before);
  p.weeks.flatMap(w=>w.tasks).find(t=>t.id==='4-5').done=true;assert.equal(info().includes('6-5'),false);
  p.deliverables.find(d=>d.id==='song1').done=true;assert.equal(info().includes('6-5'),true);
});
test('B6 a music release due on the query date is not already overdue',async()=>{
  const e=setup(),p=fixture();p.weeks.flatMap(w=>w.tasks).forEach(t=>{if(t.track==='sound')t.done=true;});
  p.weeks.flatMap(w=>w.tasks).find(t=>t.id==='4-5').dueDate='2026-10-16';p.deliverables.find(d=>d.id==='song1').dueDate='2026-10-16';
  assert.equal(e.api.projectDayInfo(p,'2026-10-16').actions.some(a=>a.taskId==='6-5'),true);
});

(async()=>{
  let failed=0;
  for(const [name,fn] of testCases){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}
  console.log(`${testCases.length-failed}/${testCases.length} file bridge tests passed.`);process.exitCode=failed?1:0;
})();
