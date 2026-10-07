/* ===== Twin: the factory page as a live digital twin.
   KPI cards, a stepper that follows one video, a queue table, a station panel, floating callouts and view tools,
   all laid over the 3D scene. Everything here is plain DOM driven by the same state as the simulation. ===== */
Object.assign(ICON,{
  plus:'<path d="M12 5v14M5 12h14"/>',minus:'<path d="M5 12h14"/>',
  rotl:'<path d="M3 12a9 9 0 109-9 9.7 9.7 0 00-6.7 2.7L3 8"/><path d="M3 3v5h5"/>',
  rotr:'<path d="M21 12a9 9 0 11-9-9 9.7 9.7 0 016.7 2.7L21 8"/><path d="M21 3v5h-5"/>',
  target:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.6"/><path d="M12 1.8v3M12 19.2v3M1.8 12h3M19.2 12h3"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
  moon:'<path d="M20.5 14.2A8.6 8.6 0 019.8 3.5a8.6 8.6 0 1010.7 10.7z"/>',
  panel:'<rect x="3" y="4.5" width="18" height="15" rx="3"/><path d="M15 4.5v15"/>',
  close:'<path d="M6 6l12 12M18 6L6 18"/>',
  eye:'<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.8"/>',
  bolt:'<path d="M13 2.5L5 13.5h6.2L10.5 21.5 19 10.5h-6.2z"/>',
  pin:'<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0113 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.4"/>'});

const PAGE_OF={brand:'brand',ideas:'ideas',make:'studio',review:'review',publish:'publish',metrics:'activity',report:'activity'};
const ICON_OF=k=>k==='make'?'studio':k;
const curStation=it=>it.c<.5?0:Math.max(1,Math.min(7,Math.round(it.c)));
const mmss=s=>{s=Math.max(0,Math.floor(s));return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')};
const fmtWait=s=>s<60?Math.max(1,Math.round(s))+'s':Math.round(s/60)+' '+t('min');
const gradOf=n=>posterBg(n);
const todDefault=()=>{try{const v=Q.get('tod')||localStorage.getItem('sv.tod');if(v==='day'||v==='night')return v}catch(e){}
  const m=document.documentElement.dataset.theme;if(m==='dark')return 'night';if(m==='light')return 'day';return matchMedia('(prefers-color-scheme: dark)').matches?'night':'day'};

const Twin={root:null,els:{},sig:'',stepKey:'',sec:-1,ro:null,safeKey:'',
  /* ---------- model ---------- */
  live(){return SIM.items.filter(i=>!i.dead)},
  tracked(){let it=SIM.items.find(i=>i.id===S.track&&!i.dead);if(!it){const l=this.live().sort((a,b)=>b.c-a.c);it=l[0]||null;S.track=it?it.id:null}return it},
  sel(){if(S.sel)return S.sel;const it=this.tracked();return it?STAGES[Math.max(0,curStation(it)-1)]:'review'},
  step(it,k){if(!it)return 'todo';if(it.c>=8)return 'done';const cs=curStation(it);return k<cs?'done':k>cs?'todo':(it.mode==='wait'?'wait':'cur')},
  compact(){return !this.root||this.root.dataset.layout==='compact'},
  panelOpen(){return S.panel===undefined?!this.compact():S.panel},
  kpis(){const need=needCount();return [
    {ic:'factory',c:'#2a62c9',l:t('kpi.flight'),v:this.live().length,s:t('kpi.flight.sub',{m:10})},
    {ic:'inbox',c:'#d98a00',l:t('kpi.need'),v:need,s:t('kpi.need.sub',{r:S.queue.length,p:S.pubq.length})+(S.fails.length?t('kpi.need.fail',{f:S.fails.length}):''),warn:need>0},
    {ic:'publish',c:'#1f9d62',l:t('kpi.posted'),v:S.done,s:t('kpi.posted.sub',{m:3})},
    {ic:'bolt',c:'#7b5cd6',l:t('kpi.tokens'),v:0,s:t('kpi.tokens.sub')}]},
  rows(k){const it=this.tracked(),here=it&&curStation(it)===STAGES.indexOf(k)+1,oldest=S.queue.concat(S.pubq).reduce((m,x)=>Math.min(m,x.since),1e9);
    const wait=S.queue.length+S.pubq.length?fmtWait(Math.max(1,SIM.time-oldest)):'—',pct=v=>Math.max(0,Math.min(100,v));
    if(k==='brand'){const v=FACTS.filter(f=>f.v).length;return [{l:t('pn.facts'),v:v+'/'+FACTS.length,p:pct(v/FACTS.length*100)},{l:t('pn.claims'),v:t('pn.active',{n:3}),p:100},{l:t('pn.voice'),v:t('pn.voice.v')},{l:t('pn.cost'),v:'0 · 0'}]}
    if(k==='ideas')return [{l:t('pn.hooks'),v:'5',p:50},{l:t('pn.guard'),v:'5/5',p:100},{l:t('pn.hints'),v:'3/5',p:60},{l:t('pn.cost'),v:'0 · 0'}];
    if(k==='make'){let p=here?(it.mode==='dwell'?pct((1-(it.until-SIM.time)/(DWELL*1.7))*100):100):(it&&it.c>3?100:0);return [{l:t('pn.render'),v:Math.round(p)+'%',p},{l:t('pn.template'),v:'brand-promo'},{l:t('pn.format'),v:'9:16 · 15 s'},{l:t('pn.cost'),v:'0 · 0'}]}
    if(k==='review')return [{l:t('pn.waiting'),v:String(S.queue.length),p:pct(S.queue.length*10),c:'#d98a00'},{l:t('pn.checklist'),v:'1/3',p:33},{l:t('pn.oldest'),v:S.queue.length?wait:'—'},{l:t('pn.cost'),v:'0 · 0'}];
    if(k==='publish')return [{l:t('pn.toconfirm'),v:String(S.pubq.length),p:pct(S.pubq.length*10),c:'#d98a00'},{l:t('pn.today'),v:S.done+'/3',p:pct(S.done/3*100)},{l:t('pn.provider'),v:t('pn.provider.v')},{l:t('pn.upload'),v:t(S.canUpload?'pn.upload.on':'pn.upload.off')}];
    if(k==='metrics')return [{l:t('pn.views'),v:'4.1k',p:41},{l:t('pn.lift'),v:'+38%',p:38},{l:t('pn.pull'),v:t('pn.pull.v')},{l:t('pn.cost'),v:'0 · 0'}];
    return [{l:t('pn.cycle'),v:String(SIM.cycle),p:pct(SIM.cycle*12)},{l:t('pn.family'),v:t('fam.tip')},{l:t('pn.hintsgen'),v:'2',p:40},{l:t('pn.cost'),v:'0 · 0'}]},
  statusOf(k){const it=this.tracked(),i=STAGES.indexOf(k)+1;
    if(k==='review'&&S.queue.length||k==='publish'&&S.pubq.length)return ['wait',t('pn.s.wait')];
    if(it&&curStation(it)===i&&it.c<8)return it.mode==='wait'?['wait',t('pn.s.wait')]:['work',t('pn.s.work')];
    return it&&it.c>i?['ok',t('pn.s.ok')]:['idle',t('pn.s.idle')]},

  /* ---------- markup ---------- */
  html(){const lay=this.layoutFor();
    return `<div class="scene-col"><div class="twin" id="twin" data-layout="${lay}" data-tod="${S.tod}" data-hud="${Q.get('hud')==='0'?0:1}"><div class="twstage"><div class="scene-wrap" id="sceneWrap"><div class="slot"></div>
      <div class="hud"><div class="hud-tl" id="twTL"><div class="ctl" id="twCtl"></div><div class="kpis" id="twKpis"></div><div class="hint only3d">${t('hint.3d')}</div></div><div class="pins" id="twPins"></div><aside class="panel hud-card" id="twPanel"></aside></div></div>
      <section class="stepper hud-card" id="twStepper"></section><section class="qtable hud-card" id="twTable"></section></div>
      <div class="dock" id="dock" hidden></div></div></div>
      <div class="legend-row">${[['idea','state.idea'],['rendered','state.rendered'],['in_review','state.in_review'],['approved','state.approved'],['published','state.published']].map(([k,l])=>`<span><i style="background:${STATECOL[k]}"></i>${t(l)}</span>`).join('')}<span><i style="background:#7a1f1f"></i>${t('state.failed')}</span></div>`},
  layoutFor(){const f=$('#frame');return (S.view==='2d'||!THREE_OK()||(f&&f.clientWidth<880))?'compact':'overlay'},
  ctlHTML(){const run=S.loop==='running',led=run?'':S.loop==='paused'?'pause':'stop',night=S.tod==='night',open=this.panelOpen();
    return `<span class="glass live"><i class="led ${led}"></i><span>${t('loop.'+S.loop)}</span><em class="mono" id="twClock">${mmss(SIM.time)}</em></span>
    <button class="glass ib" data-act="pause" aria-label="${run?t('loop.pause'):t('loop.resume')}">${ico(run?'pause':'play','width="14" height="14"')}<span>${run?t('loop.pause'):t('loop.resume')}</span></button>
    <button class="glass ib" data-act="stop" aria-label="${t('loop.stop')}">${ico('stop','width="13" height="13"')}<span>${t('loop.stop')}</span></button>
    <span class="tools" role="toolbar"><button class="tbtn only3d wide" data-act="zoomin" aria-label="${t('tool.zin')}" title="${t('tool.zin')}">${ico('plus')}</button><button class="tbtn only3d wide" data-act="zoomout" aria-label="${t('tool.zout')}" title="${t('tool.zout')}">${ico('minus')}</button><button class="tbtn only3d wide" data-act="rotl" aria-label="${t('tool.rotl')}" title="${t('tool.rotl')}">${ico('rotl')}</button><button class="tbtn only3d wide" data-act="rotr" aria-label="${t('tool.rotr')}" title="${t('tool.rotr')}">${ico('rotr')}</button><button class="tbtn only3d" data-act="resetview" aria-label="${t('tool.reset')}" title="${t('tool.reset')}">${ico('target')}</button><button class="tbtn only3d" data-act="tod" aria-label="${night?t('tool.day'):t('tool.night')}" title="${night?t('tool.day'):t('tool.night')}">${ico(night?'sun':'moon')}</button><button class="tbtn" data-act="panel" aria-pressed="${open}" aria-label="${t('tool.panel')}" title="${t('tool.panel')}">${ico('panel')}</button></span>`},
  kpisHTML(){return this.kpis().map(k=>`<div class="kpi hud-card ${k.warn?'warn':''}" style="--c:${k.c}"><span class="ki">${ico(k.ic)}</span><div><small>${k.l}</small><b>${k.v}</b><em>${esc(k.s)}</em></div></div>`).join('')},
  stepperHTML(){const it=this.tracked(),cs=it?curStation(it):0,k0=STAGES[Math.max(0,cs-1)],cap=it?`${t('station.'+k0)} · ${it.mode==='wait'?t('st.wait'):it.c>=8?t('pn.s.ok'):t('st.work')}`:t('st.idle');
    const steps=STAGES.map((k,i)=>{const s=this.step(it,i+1),tm=it&&it.times&&it.times[i+1],sub=s==='done'?(tm?fmtT(tm):'✓'):s==='wait'?t('st.waitshort'):s==='cur'?t('st.workshort'):'—';
      return `<li class="${s}" style="--sc:${SC[k]}"><button data-act="selstation" data-k="${k}" aria-label="${t('station.'+k)}"><span class="sd">${s==='done'?ico('check'):ico(ICON_OF(k))}</span><b>${t('station.'+k)}</b><small>${sub}</small></button></li>`}).join('');
    return `<header><span class="th" style="background:${it?gradOf(it.n):'#cfd9d5'}"></span><div class="ti"><small>${t('st.following')}</small><b>${it?esc(it.hook):t('st.idle')}</b></div>${it?`<span class="stc" style="--chipc:${STATECOL[it.state]||'#999'}">${t('state.'+it.state)}</span><span class="idc mono">${it.id}</span>`:''}</header>
    <div class="track"><div class="line"><i class="fill" id="twFill"></i></div><span class="marker" id="twMarker" style="background:${it?gradOf(it.n):'#cfd9d5'}" ${it?'':'hidden'}></span><ol class="steps">${steps}</ol></div><p class="cap">${esc(cap)}</p>`},
  tableHTML(){const live=this.live().sort((a,b)=>b.c-a.c),need=S.queue.length+S.pubq.length+S.fails.length,tab=S.tab3||'live';
    const th=n=>`<span class="th" style="background:${gradOf(n)}"></span>`,wait=x=>t('q.waited',{w:fmtWait(Math.max(1,SIM.time-x.since))});let rows='';
    if(tab==='live')rows=live.map(it=>{const at=STAGES[Math.max(0,curStation(it)-1)];return `<button class="qrow ${it.id===S.track?'on':''}" data-act="qrow" data-kind="live" data-id="${it.id}">${th(it.n)}<span class="tx"><b>${esc(it.hook)}</b><small>${it.id} · ${t('station.'+at)}</small></span><span class="stc" style="--chipc:${STATECOL[it.state]||'#999'}">${t('state.'+it.state)}</span></button>`}).join('')||`<p class="qe">${t('q.empty.live')}</p>`;
    else if(tab==='need'){rows=S.queue.map(q=>`<button class="qrow" data-act="qrow" data-kind="review" data-id="${q.id}">${th(q.n)}<span class="tx"><b>${esc(q.hook)}</b><small>${q.id} · ${wait(q)}</small></span><span class="stc" style="--chipc:#d98a00">${t('q.review')}</span></button>`).join('')
      +S.pubq.map(p=>`<button class="qrow" data-act="qrow" data-kind="publish" data-id="${p.id}">${th(p.n)}<span class="tx"><b>${esc(p.hook)}</b><small>${p.id} · ${wait(p)}</small></span><span class="stc" style="--chipc:#1f9d62">${t('q.publish')}</span></button>`).join('')
      +S.fails.map(f=>`<button class="qrow" data-act="qrow" data-kind="fail" data-id="${f.id}"><span class="th" style="background:#7a1f1f"></span><span class="tx"><b>${esc(f.hook)}</b><small>${f.id}</small></span><span class="stc" style="--chipc:#c23636">${t('q.failed')}</span></button>`).join('');if(!rows)rows=`<p class="qe">${t('q.empty.need')}</p>`}
    else rows=S.posted.map(p=>`<button class="qrow" data-act="qrow" data-kind="done" data-id="${p.id}">${th(p.n)}<span class="tx"><b>${esc(p.hook)}</b><small>${p.id} · ${fmtT(p.ts)}</small></span><span class="stc" style="--chipc:${STATECOL.published}">${t('state.published')}</span></button>`).join('')||`<p class="qe">${t('q.empty.done')}</p>`;
    const tb=(v,l,n)=>`<button role="tab" data-act="qtab" data-v="${v}" aria-selected="${tab===v}">${l}<b>${n}</b></button>`;
    return `<div class="qtabs" role="tablist">${tb('live',t('q.live'),live.length)}${tb('need',t('q.need'),need)}${tb('done',t('q.done'),S.posted.length)}</div><div class="qrows">${rows}</div>`},
  panelHTML(){const k=this.sel(),[st,stl]=this.statusOf(k),role=STAGE_ROLE[k],page=PAGE_OF[k],pinned=!!S.sel;
    const rows=this.rows(k).map(r=>`<div class="pr"><div class="pl"><span>${esc(r.l)}</span><b>${esc(r.v)}</b></div>${r.p!==undefined?`<div class="pbar"><i style="width:${r.p}%;--c:${r.c||SC[k]}"></i></div>`:''}</div>`).join('');
    return `<header><span class="pic" style="background:${SC[k]}">${ico(ICON_OF(k),'width="18" height="18"')}</span><div class="pt"><b>${t('station.'+k)}</b><small>${esc(charName(role))} · <i class="sdot ${st}"></i>${stl}</small></div><div class="pbtns">${pinned?`<button class="tbtn sm" data-act="pfollow" aria-label="${t('pn.follow')}" title="${t('pn.follow')}">${ico('eye')}</button>`:''}<button class="tbtn sm" data-act="panel" aria-label="${t('pn.close')}" title="${t('pn.close')}">${ico('close')}</button></div></header>
      <div class="pmode">${pinned?t('pn.pinned'):t('pn.following')}</div><div class="pbody">${rows}</div><footer><button class="btn sm primary" data-go="${page}">${t('pn.open',{page:t('nav.'+page)})}</button></footer>`},

  /* ---------- lifecycle ---------- */
  mount(){this.root=$('#twin');if(!this.root)return;const $$$=id=>document.getElementById(id);
    this.els={tl:$$$('twTL'),ctl:$$$('twCtl'),kpis:$$$('twKpis'),panel:$$$('twPanel'),pins:$$$('twPins'),stepper:$$$('twStepper'),table:$$$('twTable')};
    this.sig='';this.stepKey='';this.sec=-1;this.safeKey='';this.relayout();this.update(true);
    if('ResizeObserver' in window){this.ro=new ResizeObserver(()=>{if(this.raf)return;this.raf=requestAnimationFrame(()=>{this.raf=0;this.relayout();this.measure()})});[document.getElementById('frame'),this.els.tl,this.els.stepper,this.els.table,this.els.panel].forEach(n=>n&&this.ro.observe(n))}},
  unmount(){if(this.ro)this.ro.disconnect();this.ro=null;this.root=null;this.els={};this.sig=''},
  relayout(){if(!this.root)return;const lay=this.layoutFor();if(this.root.dataset.layout!==lay){this.root.dataset.layout=lay;this.sig='';this.update(true)}},
  update(force){if(!this.root)return;const it=this.tracked(),k=this.sel(),
      mk=k==='make'&&it&&it.mode==='dwell'&&curStation(it)===3?Math.floor(SIM.time*4):0,
      sig=JSON.stringify([this.live().map(i=>[i.id,curStation(i),i.state,i.mode]),S.queue.map(q=>q.id),S.pubq.map(p=>p.id),S.fails.length,S.done,S.posted.length,S.track,S.sel,this.panelOpen(),S.tab3,S.tod,S.loop,S.lang,S.canUpload,this.compact(),SIM.cycle]);
    const E=this.els;
    if(!force&&sig===this.sig){if(mk!==this.mk){this.mk=mk;E.panel.innerHTML=this.panelHTML()}return}
    this.sig=sig;this.mk=mk;
    E.ctl.innerHTML=this.ctlHTML();E.kpis.innerHTML=this.kpisHTML();E.stepper.innerHTML=this.stepperHTML();E.table.innerHTML=this.tableHTML();
    E.panel.innerHTML=this.panelHTML();E.panel.classList.toggle('open',this.panelOpen());this.renderPins();this.root.dataset.tod=S.tod;this.tick(0);this.measure()},
  renderPins(){const E=this.els;if(!E.pins)return;const list=[];
    if(S.queue.length)list.push(['review',S.queue[0],t('pin.review',{n:S.queue.length}),'amber']);
    if(S.pubq.length)list.push(['publish',S.pubq[0],t('pin.publish',{n:S.pubq.length}),'amber']);
    if(S.fails.length)list.push(['bin',{n:0},t('pin.fail',{n:S.fails.length}),'red']);
    E.pins.innerHTML=list.map(([k,it,sub,cls])=>`<button class="pin hud-card ${cls}" data-act="pin" data-k="${k}" data-pin="${k}"><span class="th" style="background:${k==='bin'?'#7a1f1f':gradOf(it.n)}"></span><span class="tx"><b>${k==='bin'?t('bin'):t('station.'+k)}</b><small>${esc(sub)}</small></span></button>`).join('')},
  tick(dt){if(!this.root)return;const it=this.tracked(),E=this.els;
    const key=it?curStation(it)+':'+it.mode+':'+it.state:'-';if(key!==this.stepKey){this.stepKey=key;if(dt)this.update(true)}
    const m=document.getElementById('twMarker'),f=document.getElementById('twFill');
    if(it&&m&&f){const c=it.c,p=c<1?(c-1)*.12:c>7?1+(c-7)*.12:(c-1)/6,cl=Math.max(-.07,Math.min(1.07,p));m.style.setProperty('--p',cl);f.style.setProperty('--p',Math.max(0,Math.min(1,cl)))}
    const sec=Math.floor(SIM.time);if(sec!==this.sec){this.sec=sec;const ck=document.getElementById('twClock');if(ck)ck.textContent=mmss(SIM.time)}
    if(dt&&this.sel()==='make')this.update(false);
    this.placePins();
    if(Scene.setFx)Scene.setFx({track:it?it.id:null,sel:this.sel(),pin:S.sel,need:{review:S.queue.length>0,publish:S.pubq.length>0}})},
  placePins(){const E=this.els;if(!E.pins||!Scene.anchor||!Scene.project)return;const s=Scene.safe||{l:0,t:0,r:0,b:0},W=Scene.host?Scene.host.clientWidth:0;
    for(const el of E.pins.children){const a=Scene.anchor(el.dataset.pin);if(!a)continue;const p=Scene.project(a);el.hidden=!p.vis;if(!p.vis)continue;const hw=(el.offsetWidth||150)/2+4;
      el.style.left=Math.max(s.l+hw,Math.min(W-s.r-hw,p.x))+'px';el.style.top=Math.max(s.t+(el.offsetHeight||44)+16,p.y)+'px'}},
  measure(){const w=document.getElementById('sceneWrap'),E=this.els;if(!w||!Scene.setSafe||!E.tl)return;const wr=w.getBoundingClientRect();if(!wr.width)return;
    const rel=el=>{const r=el.getBoundingClientRect();return{l:r.left-wr.left,t:r.top-wr.top,r:r.right-wr.left,b:r.bottom-wr.top}},over=this.root.dataset.layout==='overlay',open=this.panelOpen();
    if(this.root.dataset.hud==='0'){const k0='0';if(this.safeKey!==k0){this.safeKey=k0;Scene.setSafe({l:0,t:0,r:0,b:0})}return}
    let T=rel(E.tl).b+8,B=10,L=10,R=10;
    const side=r=>(r.l+r.r)/2<wr.width/2?'l':'r',inset=r=>side(r)==='l'?{L:r.r+8}:{R:wr.width-r.l+8};
    if(over){const tb=rel(E.table),st=rel(E.stepper);w.style.setProperty('--tbl-h',Math.round(tb.b-tb.t)+'px');B=wr.height-st.t+8;
      if(open){const i=inset(tb);if(i.L)L=i.L;if(i.R)R=i.R}else B=wr.height-Math.min(st.t,tb.t)+8}
    else if(open){B=wr.height-rel(E.panel).t+8}
    const k=[T,B,L,R].map(Math.round).join(',');if(k===this.safeKey)return;this.safeKey=k;Scene.setSafe({l:L,t:T,r:R,b:B})},

  /* ---------- actions ---------- */
  select(k){S.sel=k;S.panel=true;this.update(true)},
  act(a,el){
    if(a==='zoomin'){Scene.zoomBy&&Scene.zoomBy(1/1.18);return true}
    if(a==='zoomout'){Scene.zoomBy&&Scene.zoomBy(1.18);return true}
    if(a==='rotl'){Scene.rotateBy&&Scene.rotateBy(-.3);return true}
    if(a==='rotr'){Scene.rotateBy&&Scene.rotateBy(.3);return true}
    if(a==='tod'){S.tod=S.tod==='night'?'day':'night';try{localStorage.setItem('sv.tod',S.tod)}catch(e){}Scene.applyTod&&Scene.applyTod();this.update(true);return true}
    if(a==='panel'){S.panel=!this.panelOpen();this.update(true);return true}
    if(a==='pfollow'){S.sel=null;this.update(true);return true}
    if(a==='selstation'){this.select(el.dataset.k);return true}
    if(a==='qtab'){S.tab3=el.dataset.v;this.update(true);return true}
    if(a==='pin'){const k=el.dataset.k;if(k==='bin')go('inbox');else this.select(k);return true}
    if(a==='qrow'){const kd=el.dataset.kind;if(kd==='live'){S.track=el.dataset.id;S.sel=null;this.update(true)}else if(kd==='review')go('review');else if(kd==='publish')go('publish');else if(kd==='fail')go('inbox');else go('activity');return true}
    return false}
};
