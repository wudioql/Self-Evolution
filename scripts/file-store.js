// Shared source, embedded into each standalone HTML by sync-plan.py.
// File JSON is authoritative. Cache is an explicit, recoverable draft only.
const deepCopy = value => JSON.parse(JSON.stringify(value));
const escapeHTML = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function projectToday() {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(p => [p.type,p.value]));
  return values.year+'-'+values.month+'-'+values.day;
}
function projectStamp() { return new Date().toISOString(); }
function dayNumber(ds, origin) { return Math.round((Date.parse(ds+'T00:00:00Z')-Date.parse(origin+'T00:00:00Z'))/86400000); }
function addDays(ds, n) { return new Date(Date.parse(ds+'T00:00:00Z')+n*86400000).toISOString().slice(0,10); }
function validDate(ds) { return typeof ds==='string' && /^\d{4}-\d{2}-\d{2}$/.test(ds) && !ds.startsWith('0000-') && Number.isFinite(Date.parse(ds+'T00:00:00Z')) && addDays(ds,0)===ds; }
function must(test, message) { if(!test) throw new Error(message); }
function recordEvent(data, action, details={}) {
  if(!Array.isArray(data.history)) data.history=[];
  data.history.push({at:projectStamp(),action,...details});
}
function planStats(p) {
  const list=p.weeks.flatMap(w=>w.tasks), done=list.filter(t=>t.done).length;
  return {totalTasks:list.length,doneTasks:done,pct:list.length?Math.round(done/list.length*100):0,
          delivDone:p.deliverables.filter(d=>d.done).length,delivTotal:p.deliverables.length};
}
const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const hasOwn = (obj,key) => Object.prototype.hasOwnProperty.call(obj,key);
const integerNumber = (value,minimum=0) => Number.isSafeInteger(value) && value>=minimum;
const MUSIC_RELEASE_IDS = new Set(['4-5','8-2','13-2']);
function validateState(item,asOf,label='记录') {
  must(isRecord(item),label+' 必须为对象');
  must(typeof (hasOwn(item,'done')?item.done:false)==='boolean',label+'.done 必须为布尔值');
  must(typeof (hasOwn(item,'note')?item.note:'')==='string',label+'.note 必须为文本');
  const evidence=hasOwn(item,'evidence')?item.evidence:[];
  must(Array.isArray(evidence)&&evidence.every(x=>typeof x==='string'),label+'.evidence 必须为文本数组');
  must(item.completedOn==null||typeof item.completedOn==='string',label+'.completedOn 必须为日期或 null');
  if(item.completedOn) must(validDate(item.completedOn)&&item.completedOn<=asOf&&item.done===true,label+' 的完成日期无效、在未来或尚未完成');
}
function validateDailyState(checkins,logs,meta,asOf,allowDuplicates=false) {
  must(Array.isArray(checkins),'checkins 必须为日期数组');
  const validActual=ds=>validDate(ds)&&meta.day0<=ds&&ds<=meta.end&&ds<=asOf;
  must(checkins.every(validActual),'打卡日期必须在本计划内且不能在未来');
  must(allowDuplicates||new Set(checkins).size===checkins.length,'打卡日期重复');
  must(isRecord(logs),'dailyLogs 必须为日期索引对象');
  Object.entries(logs).forEach(([ds,log])=>{
    must(validActual(ds),'每日记录日期必须在本计划内且不能在未来');
    must(isRecord(log)&&typeof (hasOwn(log,'note')?log.note:'')==='string','每日记录 / 备注格式无效');
    if(hasOwn(log,'minutes'))must(integerNumber(log.minutes),'每日分钟必须为非负整数；未知时不填');
  });
}
function validatePlan(p,asOf=projectToday()) {
  must(validDate(asOf),'校验基准日期无效');
  must(isRecord(p)&&p.schema==='self-evolution/plan90/v2','不是 v2 进度文件；旧备份请用导入 / agent 合并。');
  const m=p.meta;
  must(isRecord(m)&&validDate(m.day0)&&validDate(m.day1)&&validDate(m.end),'计划日期无效');
  must(dayNumber(m.day1,m.day0)===1,'Day 1 必须是 Day 0 的次日');
  must(integerNumber(m.totalWeeks,1)&&integerNumber(m.totalDays,1),'周数 / 总天数必须为正整数');
  must(Array.isArray(p.weeks)&&p.weeks.length===m.totalWeeks&&m.totalDays===m.totalWeeks*7,'周数 / 总天数不一致');
  must(dayNumber(m.end,m.day0)===m.totalDays,'结束日期与总天数不一致');
  must(integerNumber(m.revision)&&typeof m.updated==='string','revision / updated 无效');
  must(validDate(m.day90)&&dayNumber(m.day90,m.day0)===90,'Day 90 日期不一致');
  if(hasOwn(m,'day98'))must(m.day98===m.end,'day98 与 end 不一致');
  must(isRecord(p.tracks)&&Object.values(p.tracks).every(v=>typeof v==='string'&&v.length>0),'轨道标签必须为非空文本');
  const seen=new Set(),index=new Map();
  function task(t){
    must(isRecord(t)&&typeof t.id==='string'&&/^[A-Za-z0-9_-]+$/.test(t.id)&&!seen.has(t.id),'重复或无效任务 ID');
    seen.add(t.id);must(hasOwn(t,'done')&&typeof t.text==='string','任务缺少状态 / 文字');validateState(t,asOf,t.id);
  }
  p.weeks.forEach((w,i)=>{
    must(isRecord(w)&&integerNumber(w.n,1)&&w.n===i+1&&validDate(w.start)&&validDate(w.end)&&
      dayNumber(w.start,m.day0)===i*7+1&&dayNumber(w.end,m.day0)===(i+1)*7,'每周日期不连续');
    must(Array.isArray(w.tasks)&&typeof (hasOwn(w,'note')?w.note:'')==='string'&&typeof w.title==='string'&&typeof w.days==='string','周任务 / 标题 / 日号 / 备注无效');
    w.tasks.forEach(t=>{
      task(t);index.set(t.id,t);
      must(typeof t.track==='string'&&hasOwn(p.tracks,t.track),'任务轨道无效');
      must(validDate(t.scheduledDate)&&validDate(t.dueDate)&&m.day0<=t.scheduledDate&&t.scheduledDate<=t.dueDate&&t.dueDate<=m.end,'任务排期越界或倒置');
      must(typeof (hasOwn(t,'optional')?t.optional:false)==='boolean','optional 必须为布尔值');
    });
  });
  must(Array.isArray(p.deliverables),'缺少交付物数组');
  p.deliverables.forEach(t=>{task(t);must(validDate(t.dueDate)&&m.day0<=t.dueDate&&t.dueDate<=m.end,'交付物截止日不在计划内');});
  index.forEach(t=>{const parents=hasOwn(t,'dependsOn')?t.dependsOn:[];
    must(Array.isArray(parents)&&parents.every(id=>typeof id==='string'&&index.has(id)&&id!==t.id),'前置任务 ID 无效');});
  must(Array.isArray(p.dailyPlan)&&p.dailyPlan.length===m.totalDays+1,'每日安排缺日');
  p.dailyPlan.forEach((d,i)=>{
    must(isRecord(d)&&integerNumber(d.day)&&d.day===i&&validDate(d.date)&&dayNumber(d.date,m.day0)===i,'每日日期不连续');
    must(integerNumber(d.budgetMinutes)&&Array.isArray(d.actions),'每日预算 / 动作无效');
    d.actions.forEach(a=>must(isRecord(a)&&typeof a.taskId==='string'&&index.has(a.taskId)&&typeof a.text==='string','每日动作引用无效'));
  });
  validateDailyState(p.checkins,hasOwn(p,'dailyLogs')?p.dailyLogs:{},m,asOf);
  const overrides=hasOwn(p,'overrides')?p.overrides:[];
  must(Array.isArray(overrides),'overrides 必须为数组');
  overrides.forEach(o=>must(isRecord(o)&&validDate(o.start)&&validDate(o.end)&&m.day0<=o.start&&o.start<=o.end&&o.end<=m.end&&
    ['night','low'].includes(o.mode)&&typeof (hasOwn(o,'note')?o.note:'')==='string','豁免日期或模式无效'));
  must(Array.isArray(p.checkpoints),'缺少复检点数组');
  p.checkpoints.forEach(c=>must(isRecord(c)&&integerNumber(c.day)&&c.day<=m.totalDays&&validDate(c.date)&&dayNumber(c.date,m.day0)===c.day&&typeof c.text==='string','复检日期无效'));
  ['history','_orphans'].forEach(k=>must(!hasOwn(p,k)||Array.isArray(p[k]),k+' 必须为数组'));
  const accums=hasOwn(p,'accumulators')?p.accumulators:[];
  must(Array.isArray(accums),'accumulators 必须为数组');
  const accSeen=new Set();
  accums.forEach(a=>{
    must(isRecord(a)&&typeof a.id==='string'&&/^[A-Za-z0-9_-]+$/.test(a.id)&&!accSeen.has(a.id),'积累项 ID 无效或重复');
    accSeen.add(a.id);
    must(typeof a.text==='string'&&a.text.trim().length>0&&typeof a.unit==='string'&&a.unit.trim().length>0,'积累项 text / unit 无效');
    must(integerNumber(a.target,1),'积累项 target 必须为正整数');
    must(['items','reported','derived'].includes(a.mode),'积累项 mode 必须为 items / reported / derived');
    if(a.mode==='derived')return;
    must(integerNumber(a.count),'累计数必须为非负整数');
    if(a.lastAddedOn!=null)must(validDate(a.lastAddedOn)&&m.day0<=a.lastAddedOn&&a.lastAddedOn<=m.end&&a.lastAddedOn<=asOf,'积累最近变化日期无效');
    if(a.mode==='items'){
      must(Array.isArray(a.items),'items 模式必须含 items 数组');
      a.items.forEach(it=>must(isRecord(it)&&validDate(it.on)&&m.day0<=it.on&&it.on<=m.end&&it.on<=asOf&&
        typeof it.text==='string'&&it.text.trim().length>0,'积累条目格式无效'));
      must(a.count===a.items.length,'累计数与 items 长度不一致');
    }
    if(hasOwn(a,'targetDue'))must(validDate(a.targetDue)&&m.day0<=a.targetDue&&a.targetDue<=m.end,'积累目标日期越界');
    ['source','note'].forEach(k=>{if(hasOwn(a,k))must(typeof a[k]==='string',a.id+'.'+k+' 必须为文本');});
    (hasOwn(a,'checkpoints')?a.checkpoints:[]).forEach(cp=>must(isRecord(cp)&&integerNumber(cp.count)&&
      typeof cp.taskId==='string'&&/^[A-Za-z0-9_-]+$/.test(cp.taskId)&&index.has(cp.taskId),'积累里程碑格式无效'));
  });
  const stats=planStats(p);must(isRecord(p.stats)&&Object.keys(p.stats).length===Object.keys(stats).length&&
    Object.keys(stats).every(k=>integerNumber(p.stats[k])&&p.stats[k]===stats[k]),'统计与任务状态不符');
}
const faultTextFields=['date','eqType','eqModel','eqId','alarmCode','causeCategory','symptom','condition','troubleshootPath','rootCause','rootCauseTag','action','prevention','links','notes'];
function validateFaults(d) {
  must(isRecord(d)&&d.schema==='self-evolution/faults/v1'&&Array.isArray(d.items),'不是故障库 JSON');
  must(isRecord(d.meta)&&integerNumber(d.meta.revision),'缺少有效 revision');
  if(hasOwn(d.meta,'nextId'))must(integerNumber(d.meta.nextId,1),'nextId 必须为正整数');
  const seen=new Set();
  d.items.forEach(i=>{
    must(isRecord(i)&&typeof i.id==='string'&&/^[A-Za-z0-9_-]+$/.test(i.id)&&!seen.has(i.id),'故障 ID 重复或无效');seen.add(i.id);
    faultTextFields.forEach(f=>must(i[f]===undefined||typeof i[f]==='string','故障字段必须为文字：'+f));
    if(i.date) must(validDate(i.date)||(/^\d{4}-\d{2}$/.test(i.date)&&validDate(i.date+'-01')),'故障日期无效');
    ['isRecurring','isSolved','isSample'].forEach(k=>must(i[k]==null||typeof i[k]==='boolean','布尔状态无效：'+k));
    must(i.downtimeMin==null||(typeof i.downtimeMin==='number'&&Number.isFinite(i.downtimeMin)&&i.downtimeMin>=0),'停机分钟无效');
  });
  ['eqTypes','categories','sensitive'].forEach(k=>must(isRecord(d.config)&&Array.isArray(d.config[k])&&d.config[k].every(x=>typeof x==='string'),'配置列表无效：'+k));
}
function mergePlanNotes(a,b) {
  a=a||'';b=b||'';
  return !b||('\n'+a+'\n').includes('\n'+b+'\n')?a:a+(a?'\n':'')+b;
}
function sameJSON(a,b) {
  if(a===b)return true;
  if(Array.isArray(a)&&Array.isArray(b))return a.length===b.length&&a.every((v,i)=>sameJSON(v,b[i]));
  if(isRecord(a)&&isRecord(b))return Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>hasOwn(b,k)&&sameJSON(a[k],b[k]));
  return false;
}
function convertLegacy(d,current,asOf=projectToday()) {
  // A v2 browser import is an explicitly opened snapshot, not a master merge.
  if(isRecord(d)&&d.schema==='self-evolution/plan90/v2'){validatePlan(d,asOf);return deepCopy(d);}
  validatePlan(current,asOf);
  must(isRecord(d)&&(d.schema===undefined||d.schema===null||d.schema==='self-evolution/plan90/v1'),'不认识的进度备份');
  let imported=[],deliveries=[],weekNotes=new Map();
  if(d.schema==='self-evolution/plan90/v1'){
    must(Array.isArray(d.weeks),'旧备份缺少 weeks 数组');const seenWeeks=new Set();
    d.weeks.forEach(w=>{
      must(isRecord(w)&&integerNumber(w.n,1)&&Array.isArray(w.tasks),'导入周格式无效');
      const n=String(w.n);must(!seenWeeks.has(n),'导入周次重复');seenWeeks.add(n);
      must(typeof (hasOwn(w,'note')?w.note:'')==='string','导入周备注必须为文本');
      imported.push(...w.tasks);if(w.note)weekNotes.set(n,w.note);
    });
    deliveries=hasOwn(d,'deliverables')?d.deliverables:[];must(Array.isArray(deliveries),'导入交付物必须为数组');
  }else{
    const done=d.done,notes=hasOwn(d,'notes')?d.notes:{},deliv=hasOwn(d,'deliv')?d.deliv:{};
    must(isRecord(done)&&isRecord(notes)&&isRecord(deliv),'不是受支持的旧浏览器状态');
    must(Object.values(notes).every(v=>typeof v==='string'),'旧备注必须是文本索引');
    weekNotes=new Map(Object.entries(notes).filter(([k])=>/^[1-9][0-9]*$/.test(k)));
    const noteIds=Object.keys(notes).filter(k=>!weekNotes.has(k)&&!hasOwn(deliv,k));
    const ids=[...new Set(Object.keys(done).concat(noteIds))];
    imported=ids.map(id=>({id,done:hasOwn(done,id)?done[id]:false,note:hasOwn(notes,id)?notes[id]:''}));
    deliveries=Object.entries(deliv).map(([id,done])=>({id,done,note:hasOwn(notes,id)?notes[id]:''}));
  }
  const seen=new Set();
  imported.concat(deliveries).forEach(t=>{
    must(isRecord(t)&&typeof t.id==='string'&&/^[A-Za-z0-9_-]+$/.test(t.id)&&!seen.has(t.id),'导入中存在重复 / 无效 ID');
    seen.add(t.id);validateState(t,asOf,'导入记录 '+t.id);
  });
  const checkins=hasOwn(d,'checkins')?d.checkins:[],logs=hasOwn(d,'dailyLogs')?d.dailyLogs:{},orphans=hasOwn(d,'_orphans')?d._orphans:[];
  validateDailyState(checkins,logs,current.meta,asOf,true);
  must(Array.isArray(orphans),'_orphans 必须为数组');orphans.forEach(t=>validateState(t,asOf,'导入归档记录'));
  const p=deepCopy(current),idx=new Map(p.weeks.flatMap(w=>w.tasks).concat(p.deliverables).map(t=>[t.id,t]));
  if(!hasOwn(p,'_orphans'))p._orphans=[];
  const keep=t=>{if(!p._orphans.some(old=>sameJSON(old,t)))p._orphans.push(deepCopy(t));};
  imported.concat(deliveries).forEach(t=>{
    const to=idx.get(t.id);if(!to){keep(t);return;}
    to.done=to.done||(t.done===true);to.note=mergePlanNotes(to.note,t.note);
    to.evidence=[...new Set((to.evidence||[]).concat(t.evidence||[]))];
    if(to.done&&!to.completedOn&&t.completedOn)to.completedOn=t.completedOn;
  });
  const weeks=new Map(p.weeks.map(w=>[String(w.n),w]));
  weekNotes.forEach((note,n)=>{if(weeks.has(n)){const w=weeks.get(n);w.note=mergePlanNotes(w.note,note);}
    else if(note)keep({id:'week-'+n,kind:'week-note',note});});
  p.checkins=[...new Set(p.checkins.concat(checkins))].sort();
  if(!hasOwn(p,'dailyLogs'))p.dailyLogs={};
  Object.entries(logs).forEach(([ds,log])=>{
    const to=hasOwn(p.dailyLogs,ds)?p.dailyLogs[ds]:(p.dailyLogs[ds]={});
    to.note=mergePlanNotes(to.note,log.note);Object.entries(log).forEach(([k,v])=>{if(!hasOwn(to,k))Object.defineProperty(to,k,{value:deepCopy(v),enumerable:true,writable:true,configurable:true});});
  });
  orphans.forEach(keep);p.stats=planStats(p);validatePlan(p,asOf);
  recordEvent(p,'legacy-import-draft',{summary:'旧备份经整包校验后合并为草稿；按 ID 保留状态与备注，不改当前排期'});
  return p;
}

function sampleItem(i) { return !!i.isSample||String(i.id).startsWith('sample')||String(i.symptom||'').includes('【示例'); }
function downloadText(name,text,mime='application/json') {
  const url=URL.createObjectURL(new Blob([text],{type:mime})), a=document.createElement('a');
  a.href=url;a.download=name;document.body.appendChild(a);a.click();
  setTimeout(()=>{URL.revokeObjectURL(url);a.remove();},1000);
}
class ProjectFileStore {
  constructor({initial,fileHint,validator,onChange,normalize=d=>d,convert=d=>d,legacyKey=''}) {
    validator(initial);
    this.data=deepCopy(initial);this.fileHint=fileHint;this.validator=validator;this.onChange=onChange;
    this.normalize=normalize;this.convert=convert;this.legacyKey=legacyKey;
    this.mode='snapshot';this.handle=null;this.baseRaw=null;this.queue=Promise.resolve();
    this.cacheKey='selfevo_draft_'+initial.schema;this.cacheOK=true;this.cached=null;this.legacy=null;
    try{this.cached=JSON.parse(localStorage.getItem(this.cacheKey)||'null');this.legacy=JSON.parse(localStorage.getItem(legacyKey)||'null');}
    catch(e){this.cacheOK=false;}
  }
  status(error='') {
    const el=document.getElementById('sourceStatus');
    if(!el)return;
    const rev='revision '+this.data.meta.revision+' · '+this.data.meta.updated;
    let text=this.mode==='file'?'已写入 / 连接文件：'+this.handle.name+' · '+rev:
      this.mode==='draft'?'浏览器草稿（未写入项目）：'+rev+'。请导出后交给 agent 合并。':
      '文件快照（只读） · '+rev+'。直接告诉 agent 查询 / 勾选即可；agent 同步后重开此文件。';
    if(error)text=error+' 当前修改未写入文件。可先重新载入，再重试。';
    if(this.mode==='draft'&&!this.cacheOK)text+=' 此环境也不能保存缓存，关闭会丢失草稿，请先导出。';
    el.textContent=text;el.className='banner '+(error?'err':this.mode==='draft'?'':'info');
    const b=document.getElementById('connBtn');if(b)b.textContent=this.mode==='file'?'重新选择文件':'连接项目 JSON（可选）';
    const restore=document.getElementById('restoreBtn');if(restore)restore.hidden=!(this.cached||this.legacy);
  }
  refresh() { this.onChange(this.data);this.status(); }
  async connect() {
    if(!window.showOpenFilePicker){this.status('此浏览器不能直接写文件。可由 agent 操作，或临时编辑后导出 JSON。');return false;}
    if(this.mode==='draft'&&!confirm('连接会读取所选文件并替换当前草稿。未导出的草稿可能丢失；继续？'))return false;
    try{
      await this.queue.catch(()=>{});
      const [h]=await window.showOpenFilePicker({types:[{description:'项目 JSON',accept:{'application/json':['.json']}}],multiple:false});
      const file=await h.getFile(), raw=await file.text(), next=JSON.parse(raw);this.validator(next);
      if(h.name!==this.fileHint.split('/').pop()&&!confirm('你选择的是 '+h.name+'，不是建议的 '+this.fileHint+'。之后只会写入所选文件。继续？'))return false;
      let permission=await h.queryPermission({mode:'readwrite'});
      if(permission!=='granted')permission=await h.requestPermission({mode:'readwrite'});
      if(permission!=='granted')throw new Error('未授予文件写入权限');
      this.handle=h;this.baseRaw=raw;this.data=deepCopy(next);this.mode='file';this.refresh();return true;
    }catch(e){if(e.name!=='AbortError')this.status('连接失败：'+e.message);return false;}
  }
  async reload() {
    await this.queue.catch(()=>{});
    if(this.mode==='file'){
      try{const raw=await (await this.handle.getFile()).text(), d=JSON.parse(raw);this.validator(d);
        this.data=d;this.baseRaw=raw;this.refresh();return true;
      }catch(e){this.status('读取失败：'+e.message);return false;}
    }
    if(this.mode==='draft'&&!confirm('重新打开快照会放下当前草稿；请先导出。继续？'))return false;
    location.reload();return true;
  }
  enableDraft() {
    if(!confirm('临时编辑不会写入项目文件；浏览器缓存不是正式记录。完成后须导出 JSON 交给 agent。继续？'))return false;
    this.mode='draft';this.handle=null;this.baseRaw=null;this.refresh();return true;
  }
  restoreDraft() {
    if(!confirm('恢复的可能是旧草稿；仅供核对，不会覆盖项目 JSON。需要并入项目时交给 agent。继续？'))return false;
    try{const next=this.convert(deepCopy(this.cached||this.legacy),this.data);this.validator(next);
      this.data=next;this.mode='draft';this.handle=null;this.baseRaw=null;this.refresh();return true;
    }catch(e){this.status('草稿无效：'+e.message);return false;}
  }
  async importFile(file) {
    if(!file)return false;
    try{
      const next=this.convert(JSON.parse(await file.text()),this.data);this.validator(next);
      if(!confirm('导入只打开为临时草稿，不写回任何项目文件。项目内合并可直接交给 agent。继续？'))return false;
      await this.queue.catch(()=>{});
      this.data=deepCopy(next);this.mode='draft';this.handle=null;this.baseRaw=null;this.refresh();return true;
    }catch(e){this.status('导入失败：'+e.message);return false;}
  }
  update(mutator) {
    const work=this.queue.catch(()=>{}).then(async()=>{
      if(this.mode==='snapshot')throw new Error('当前为只读快照；请通过对话让 agent 修改，或先连接 JSON / 开启临时编辑');
      const next=deepCopy(this.data);
      await mutator(next);
      next.meta.revision=this.data.meta.revision+1;next.meta.updated=projectStamp();
      this.normalize(next);this.validator(next);
      const raw=JSON.stringify(next,null,2)+'\n';
      if(this.mode==='file'){
        const latest=await (await this.handle.getFile()).text();
        if(latest!==this.baseRaw)throw new Error('检测到 agent / 其他窗口更新，已拒绝覆盖');
        let writer;
        try{writer=await this.handle.createWritable();await writer.write(raw);await writer.close();}
        catch(e){if(writer&&writer.abort)try{await writer.abort();}catch(_){};throw e;}
        this.baseRaw=raw;
      }else{
        try{localStorage.setItem(this.cacheKey,raw);this.cached=deepCopy(next);this.cacheOK=true;}
        catch(e){this.cacheOK=false;}
      }
      this.data=next;this.refresh();return true;
    });
    this.queue=work;
    return work.catch(e=>{this.onChange(this.data);this.status(e.message);return false;});
  }
  exportJSON() { downloadText(this.fileHint.split('/').pop().replace('.json','_'+projectToday()+'.local.json'),JSON.stringify(this.data,null,2)+'\n'); }
}
function projectDayInfo(p,ds) {
  const day=dayNumber(ds,p.meta.day0), plan=p.dailyPlan.find(d=>d.date===ds), index=Object.fromEntries(p.weeks.flatMap(w=>w.tasks).map(t=>[t.id,t]));
  const matches=(p.overrides||[]).filter(o=>o.start<=ds&&ds<=o.end);
  const mode=matches.some(o=>o.mode==='night')?'night':matches.length?'low':'normal';
  const overdue=Object.values(index).filter(t=>!t.done&&!t.optional&&t.dueDate<ds);
  let actions=plan?plan.actions.filter(a=>!index[a.taskId].done).map(a=>({...a,optional:!!index[a.taskId].optional})):[];
  const current=actions.find(a=>!a.optional)||actions[0];
  if(current){const pending=(index[current.taskId].dependsOn||[]).map(id=>index[id]).filter(t=>t&&!t.done);
    if(pending.length){const t=pending[0];actions.unshift({taskId:t.id,text:'先推进前置任务：'+t.text+'（只做一小步，不要求一次补完）',optional:false});}}
  if(!actions.length&&day>=1&&day<=p.meta.totalDays){
    const next=Object.values(index).filter(t=>!t.done&&!t.optional&&t.scheduledDate<=ds).sort((a,b)=>a.dueDate.localeCompare(b.dueDate)||a.id.localeCompare(b.id))[0];
    if(next)actions=[{taskId:next.id,text:'推进未完的一小步：'+next.text,optional:false}];
  }
  const ipaPaused=overdue.some(t=>t.track==='sound'||MUSIC_RELEASE_IDS.has(t.id))||p.deliverables.some(d=>d.id.startsWith('song')&&!d.done&&d.dueDate<ds);
  if(ipaPaused)actions=actions.filter(a=>index[a.taskId].track!=='ipa');
  if(mode==='night')actions=[];
  else if(mode==='low')actions=actions.filter(a=>!a.optional).slice(0,1);
  else actions=actions.slice(0,3);
  return {day,mode,actions,overdueCount:overdue.length,ipaPaused,budgetMinutes:mode==='night'?10:mode==='low'?25:plan?plan.budgetMinutes:0};
}
