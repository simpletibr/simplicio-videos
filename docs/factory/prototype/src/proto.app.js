/* ===== app: state, i18n, simulation, scene, pages ===== */
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const Q=new URLSearchParams(location.search);
const PAGES=['factory','inbox','brand','ideas','studio','review','publish','activity','settings'];
const TABS_MOBILE=['factory','inbox','review','publish','more'];
const S={device:Q.get('device')||'desktop',theme:TH[Q.get('theme')]?Q.get('theme'):'br',
  lang:Q.get('lang')?(Q.get('lang')==='en'?'en':'pt-BR'):((navigator.language||'en').toLowerCase().startsWith('pt')?'pt-BR':'en'),
  rtl:Q.get('rtl')==='1',page:PAGES.concat(['login']).includes(Q.get('page'))?Q.get('page'):'factory',tab:Q.get('tab')||'appearance',
  view:Q.get('view')||(ART.chars.brander?'3d-sprites':'3d'),auto:Q.get('auto')==='1',keep:Q.get('keep')==='1',loop:'running',reduce:false,canUpload:Q.get('upload')==='1',more:false,full:Q.get('full')==='1',
  queue:[],pubq:[],fails:[],events:[],rv:0,stale:false,otp:'',loginErr:false,done:0,idea:{n:5,adding:false},route:'det',
  doc:{running:false,ran:false},upd:false,clean:false,hold:null,studio:{rendered:false,rendering:false},logged:Q.get('page')?true:false,
  tod:'day',wx:Q.get('wx')||'clear',ptab:Q.get('ptab')==='chat'?'chat':'details',stab:Q.get('stab')||(Q.get('panel')==='1'?(Q.get('ptab')==='chat'?'bots':'details'):'follow'),snap:Q.get('snap')||(Q.get('panel')==='1'?'half':'peek'),bot:Q.get('bot')||'gatekeeper',track:null,sel:null,panel:Q.get('panel')?Q.get('panel')==='1':undefined,tab3:Q.get('tab3')||'live',posted:[]};
const RAILK='sv.rail';try{S.rail=Q.get('rail')?Q.get('rail')==='min':localStorage.getItem(RAILK)==='1'}catch(e){S.rail=Q.get('rail')==='min'}
const lk=()=>S.lang==='pt-BR'?1:0;
function t(k,p){const e=D[k];if(!e){if(!t.w[k]){t.w[k]=1;console.warn('missing i18n',k)}return k}let s=e[lk()];if(p)s=s.replace(/\{(\w+)\}/g,(m,n)=>p[n]!==undefined?p[n]:m);return s}t.w={};
const LG=()=>S.lang==='pt-BR'?'pt':'en';
const TCUR=()=>TH[S.theme];
const hex=s=>{let h=0;for(const c of s)h=(h*31+c.charCodeAt(0))>>>0;return h.toString(16).padStart(8,'0')+'a7c4e1'};
const fmtT=d=>d.toTimeString().slice(0,8);
const LOGO=`<svg width="26" height="26" viewBox="0 0 28 28" aria-hidden="true"><rect x="1" y="14" width="26" height="9" rx="4.5" fill="var(--accent)"/><circle cx="8" cy="18.5" r="1.6" fill="var(--accent-ink)"/><circle cx="14" cy="18.5" r="1.6" fill="var(--accent-ink)"/><circle cx="20" cy="18.5" r="1.6" fill="var(--accent-ink)"/><rect x="5" y="5" width="8" height="7" rx="2" fill="var(--fg)"/><rect x="16" y="8" width="7" height="4" rx="1.5" fill="var(--fg)" opacity=".55"/></svg>`;

/* ---------- sample data ---------- */
const HOOKS={en:['3 mistakes when choosing a coffee grinder','Why your espresso tastes bitter (and the 10-second fix)','Free shipping over $50: what is in the box?','The water temperature that changes everything','Your morning ritual, upgraded'],
 'pt-BR':['3 erros ao escolher um moedor de café','Por que seu espresso fica amargo (e o ajuste de 10 segundos)','Frete grátis acima de R$ 150: o que vem na caixa?','A temperatura da água que muda tudo','Seu ritual da manhã, melhorado']};
const FAM=['mistakes','question','offer','tip','ritual'];
const heroImg=()=>S.tod==='night'&&ART.hero.night?ART.hero.night:(ART.hero.day||'');
const GRADS=[['#3a2418','#c98b4a'],['#1d2b3a','#4a8fc9'],['#2a3a1d','#8fc94a'],['#3a1d2e','#c94a8f'],['#1d3a36','#4ac9b8']];
const posterBg=n=>{const k=(n||1)%5,u=ART.posters[k];return u?`linear-gradient(180deg,rgba(0,0,0,.28),rgba(0,0,0,.04) 40%,rgba(0,0,0,.5)),url(${u}) center/cover`:`linear-gradient(160deg,${GRADS[k][0]},${GRADS[k][1]})`};
const FACTS=[
 {id:'F1',en:'Free shipping over $50',pt:'Frete grátis acima de R$ 150',src:'/shipping',origin:'extracted',v:true},
 {id:'F2',en:'Roasted weekly in small batches',pt:'Torrado toda semana, em pequenos lotes',src:'/about',origin:'extracted',v:true},
 {id:'F3',en:'30-day return policy',pt:'30 dias para devolução',src:'/returns',origin:'extracted',v:true},
 {id:'F4',en:'Single-origin beans from 4 farms',pt:'Grãos de origem única de 4 fazendas',src:'/beans',origin:'extracted',v:false},
 {id:'F5',en:'Ships within 24 hours',pt:'Envio em até 24 horas',src:'/shipping',origin:'extracted',v:false},
 {id:'F6',en:'Family-owned since 2014',pt:'Empresa familiar desde 2014',src:'',origin:'user',v:true}];
const ACCTS=[{pf:'TT',c:'#111',name:'TikTok',h:'@acmecoffee',ok:true,used:1},{pf:'IG',c:'#c13584',name:'Instagram Reels',h:'@acme.coffee',ok:true,used:0},{pf:'YT',c:'#d62828',name:'YouTube Shorts',h:'Acme Coffee',ok:false,used:0}];
const PLUGINS=[['brand','stage','stable',['network']],['ideas','stage','stable',[]],['studio','stage','stable',['engine']],['review','stage','stable',[]],['publish','stage','stable',['can_publish']],['realoficial','publisher','stable',['network','secrets','can_publish']],['metrics','metrics','stable',['network']],['server','surface','stable',['local network']],['theme','data','stable',[]],['loop','host','stable',[]]];
const NAMES={br:{en:{brander:'Brush',ideator:'Spark',director:'Clapper',gatekeeper:'Gate',poster:'Post',analyst:'Lens',reflector:'Mirror',evolver:'Sprout'},pt:{brander:'Pincel',ideator:'Fagulha',director:'Claquete',gatekeeper:'Portão',poster:'Correio',analyst:'Lupa',reflector:'Espelho',evolver:'Broto'}}};
const charName=r=>{const n=NAMES[S.theme];return n?n[LG()][r]:t('role.'+r)};
const SC={brand:'#2a62c9',ideas:'#e0a21a',make:'#7b5cd6',review:'#e5483b',publish:'#1f9d62',metrics:'#1b9aaa',report:'#c2548a'};

/* ---------- events and bubbles ---------- */
let EVN=0;
const STAGE_OF={'brand.checked':'brand','ideas.generated':'ideas','make.started':'make','make.rendered':'make','item.failed':'make','gate.review':'review','review.approved':'review','review.discarded':'review','review.changes':'review','publish.previewed':'publish','gate.publish':'publish','publish.published':'publish','metrics.ingested':'metrics','report.generated':'report','hints.generated':'report'};
function phrase(ev){return t('ev.'+ev.kind,ev.data)}
function emit(kind,data){const ev={id:++EVN,ts:new Date(),kind,data:data||{},stage:STAGE_OF[kind]||null};S.events.unshift(ev);if(S.events.length>120)S.events.pop();bubbleFor(ev);Chat.fromEvent(ev);refresh('events');return ev}
function bubbleFor(ev){if(!Scene.host||!ev.stage||Scene.hidden)return;Scene.bubble(ev)}

/* ---------- simulation (canonical progress: 0..8, station k sits at k) ---------- */
const SIM={items:[],spawn:1.2,next:1,time:0,cycle:1,anchors:{}};
const SPEED=150,GAP_PX=72,DWELL=1.2;
const GATES={review:{at:4-.34,kind:'review'},publish:{at:5-.34,kind:'publish'}};
function mkItem(){const i=SIM.next++,h=HOOKS[S.lang][(i-1)%5];return{id:'itm_'+String(i).padStart(2,'0'),n:i,t0:SIM.time,times:{},hook:h,fam:FAM[(i-1)%5],c:0,mode:'move',until:0,state:'idea',passed:{},gold:i%3===0,cracked:false,fade:0,after:null,q:null}}
function segLen(c){const v=Scene.variant||'landscape',a=SIM.anchors[v],i=Math.min(7,Math.max(0,Math.floor(c)));return Math.max(60,(a[i+1]-a[i])*(SIM.len[v]))}
function stepSim(dt){
  if(S.loop!=='running')return;SIM.time+=dt;for(const d of SIM.items)if(d.dead)d.fade+=dt*1.6;
  const live=SIM.items.filter(i=>!i.dead);
  SIM.spawn-=dt;if(SIM.spawn<=0&&live.length<3&&live.every(i=>i.c>1.1)){SIM.items.push(mkItem());SIM.spawn=4.5}
  const order=[...live].sort((a,b)=>b.c-a.c);let ahead=null;
  for(const it of order){
    if(it.mode==='dwell'){if(SIM.time>=it.until){it.mode='move';if(it.after){const f=it.after;it.after=null;f(it)}}else{ahead=it;continue}}
    if(it.mode==='wait'){ahead=it;continue}
    let target=it.c+SPEED*dt/segLen(it.c);
    if(ahead){const lim=ahead.c-GAP_PX/segLen(ahead.c);target=Math.min(target,Math.max(it.c,lim))}
    for(let k=1;k<=7;k++){if(it.passed[k])continue;const g=k===4?GATES.review:k===5?GATES.publish:null;const at=g?g.at:k;
      if(it.c<=at&&target>=at){target=at;it.passed[k]=true;arrive(it,k);break}}
    it.c=Math.max(it.c,target);ahead=it;
    if(it.c>=8&&it.mode==='move'){it.dead=true}
  }
  if(S.auto)for(const q of [...S.queue])if(q.sim&&SIM.time-q.since>2.4)approve(q,true);
  if(S.auto)for(const p of [...S.pubq])if(p.sim&&SIM.time-p.since>2.4)confirmPost(p,true);
  SIM.items=SIM.items.filter(i=>!i.dead||i.fade<1);
}
function dwell(it,s,after){it.mode='dwell';it.dwl=s;it.until=SIM.time+s;it.after=after||null}
function arrive(it,k){
  (it.times=it.times||{})[k]=new Date();
  if(k===1){emit('brand.checked',{facts:FACTS.length});dwell(it,DWELL)}
  else if(k===2){it.state='drafted';emit('ideas.generated',{n:5});dwell(it,DWELL)}
  else if(k===3){emit('make.started');dwell(it,DWELL*1.7,x=>{x.state='rendered';emit('make.rendered',{s:15})})}
  else if(k===4){it.mode='wait';it.state='in_review';const q={id:it.id,hook:it.hook,fam:it.fam,n:it.n,sim:it,since:SIM.time,dur:15,hash:hex(it.id+it.hook)};S.queue.push(q);it.q=q;emit('gate.review');refresh('gate')}
  else if(k===5){it.mode='wait';it.state='scheduled';const p={id:it.id,hook:it.hook,fam:it.fam,n:it.n,sim:it,since:SIM.time,hash:hex('pub'+it.id)};S.pubq.push(p);it.p=p;emit('publish.previewed',{n:2,when:t('when.slot')});emit('gate.publish');refresh('gate')}
  else if(k===6){it.state='measured';emit('metrics.ingested',{d:3,views:'4,1k',delta:'+38%'});dwell(it,DWELL)}
  else if(k===7){it.state='archived';emit('report.generated',{family:t('fam.'+it.fam),n:9});setTimeout(()=>emit('hints.generated',{family:t('fam.'+it.fam)}),900);SIM.cycle++;dwell(it,DWELL*1.4)}
}
function approve(q,auto){const i=S.queue.indexOf(q);if(i<0)return;S.queue.splice(i,1);if(S.rv>=S.queue.length)S.rv=Math.max(0,S.queue.length-1);
  const it=q.sim;emit('review.approved',{auto:auto?1:0});
  if(it){it.state='approved';it.mode='move'}else{S.pubq.push({id:q.id,hook:q.hook,fam:q.fam,n:q.n,since:SIM.time,hash:hex('pub'+q.id)})}
  refresh('gate')}
function discard(q,kind){const i=S.queue.indexOf(q);if(i<0)return;S.queue.splice(i,1);if(S.rv>=S.queue.length)S.rv=Math.max(0,S.queue.length-1);emit(kind==='changes'?'review.changes':'review.discarded');
  if(q.sim){q.sim.dead=true;q.sim.cracked=kind!=='changes'}refresh('gate')}
function confirmPost(p,auto){const i=S.pubq.indexOf(p);if(i<0)return;S.pubq.splice(i,1);emit('publish.published',{auto:auto?1:0});S.done++;S.posted.unshift({id:p.id,hook:p.hook,n:p.n,ts:new Date()});
  const it=p.sim;if(it){it.state='published';it.mode='dwell';it.until=SIM.time+DWELL;it.after=null}refresh('gate');toast(t('toast.posted'))}
function failItem(){const it=SIM.items.filter(i=>!i.dead&&i.c>.5&&i.mode!=='wait').sort((a,b)=>b.c-a.c)[0];if(!it){toast(t('toast.nothing'));return}
  it.dead=true;it.cracked=true;S.fails.push({id:it.id,hook:it.hook});emit('item.failed');refresh('gate')}

/* ---------- scene ---------- */
const SceneSVG={host:null,svg:null,variant:null,path:null,len:{},charPos:{},ro:null,hidden:false,els:new Map(),
  pick(){return $('#frame').clientWidth>=880?'landscape':'portrait'},
  mount(h){this.host=h;h.dataset.mode='svg';this.build();this.ro=('ResizeObserver' in window)?new ResizeObserver(()=>{if(this.pick()!==this.variant)this.build();this.layout()}):null;if(this.ro)this.ro.observe($('#frame'))},
  unmount(){if(this.ro)this.ro.disconnect();this.host=null;this.svg=null;this.els.clear()},
  build(){this.variant=this.pick();const th=TCUR(),slot=$('.slot',this.host);slot.innerHTML=sceneSVG(th,this.variant,{uid:'m'});this.svg=slot.firstChild;
    this.host.style.setProperty('--scene-bg',th.p.sky1);this.path=$('#beltPath',this.svg);this.els.clear();
    const g=GEO[this.variant],pos={};STAGES.forEach(s=>{const [sx,sy,side]=g.st[s],pl=place(side,sx,sy),k=this.variant==='portrait'?.95:.9;pos[STAGE_ROLE[s]]={x:pl.cx,y:pl.cy-0*k}});pos.evolver={x:pos.reflector.x,y:pos.reflector.y};this.charPos=pos;
    $$('[data-lab]',this.svg).forEach(n=>{const k=n.getAttribute('data-lab');n.textContent=k==='bin'?t('bin'):t('station.'+k)});
    this.barriers();this.layout()},
  barriers(){const g=$('#barriers',this.svg),v=this.variant,a=SIM.anchors[v],len=SIM.len[v];let h='';
    [['review',4],['publish',5]].forEach(([k,idx])=>{const c=GATES[k].at+.12,i=Math.floor(c),f=a[i]+(a[i+1]-a[i])*(c-i),pt=this.path.getPointAtLength(f*len),pt2=this.path.getPointAtLength(Math.min(len,f*len+4)),ang=Math.atan2(pt2.y-pt.y,pt2.x-pt.x)*180/Math.PI;
      h+=`<g transform="translate(${pt.x} ${pt.y}) rotate(${ang})" data-bar="${k}"><g class="arm" transform="rotate(90)"><rect x="-4" y="-24" width="8" height="48" rx="3" fill="#fff" stroke="${TCUR().p.ink}" stroke-width="2"/><rect x="-4" y="-18" width="8" height="9" fill="${TCUR().p.gate}"/><rect x="-4" y="0" width="8" height="9" fill="${TCUR().p.gate}"/></g></g>`});g.innerHTML=h;this.bars()},
  bars(){if(!this.svg)return;$$('[data-bar]',this.svg).forEach(n=>{const k=n.getAttribute('data-bar'),open=!S.queue.concat(S.pubq).some(x=>x.sim&&((k==='review'&&S.queue.includes(x))||(k==='publish'&&S.pubq.includes(x))));const arm=$('.arm',n);arm.setAttribute('transform',open?'rotate(10) translate(0 -12)':'rotate(90)');arm.style.opacity=open?.55:1})},
  bubble(ev){const role=STAGE_ROLE[ev.stage],pos=this.charPos[role];if(!pos)return;const old=$$('.bubble',this.host);while(old.length>=2)old.shift().remove();
    const el=document.createElement('div');el.className='bubble';el.style.setProperty('--bub',SC[ev.stage]);el.innerHTML=`<b>${esc(charName(role))}</b>${esc(phrase(ev))}`;this.host.appendChild(el);this.placeEl(el,pos.x,pos.y-(this.variant==='portrait'?112:104)-(old.length?58:0));
    const g=this.svg&&this.svg.querySelector(`[data-role="${role}"] .char`);if(g){g.classList.remove('hop');void g.getBoundingClientRect();g.classList.add('hop')}
    if(!S.keep){setTimeout(()=>el.classList.add('out'),S.reduce?5200:3800);setTimeout(()=>el.remove(),S.reduce?5800:4400)}},
  relabelBin(){this.layout()},
  layout(){const bin=$('[data-lab="bin"]',this.svg);if(bin)bin.textContent=t('bin')+(S.fails.length?' · '+S.fails.length:'')},
  place(c){const a=SIM.anchors[this.variant],i=Math.min(7,Math.floor(c)),f=a[i]+(a[i+1]-a[i])*(c-i),len=SIM.len[this.variant];return this.path.getPointAtLength(Math.min(len,Math.max(0,f*len)))},
  scale(){const r=this.svg.getBoundingClientRect(),vb=GEO[this.variant].vb;return r.width/vb[0]},
  placeEl(el,x,y){const k=this.scale();el.style.left=Math.max(24,Math.min(this.svg.getBoundingClientRect().width-24,x*k))+'px';el.style.top=Math.max(40,y*k)+'px'},
  draw(){if(!this.svg||!this.path)return;const g=$('#items',this.svg),live=SIM.items;
    for(const [id,el] of this.els)if(!live.some(i=>i.id===id)){el.remove();this.els.delete(id)}
    for(const it of live){let el=this.els.get(it.id);if(!el){el=document.createElementNS('http://www.w3.org/2000/svg','g');el.innerHTML=cartridge();g.appendChild(el);this.els.set(it.id,el)}
      const p=this.place(Math.min(it.c,7.999));el.setAttribute('transform',`translate(${p.x} ${p.y})`);
      const col=it.cracked?'#7a1f1f':STATECOL[it.state]||'#999';$('.body',el).setAttribute('fill',col);
      $('.gold',el).style.display=(it.gold&&['published','measured','archived'].includes(it.state))?'':'none';$('.crack',el).style.display=it.cracked?'':'none';
      el.style.opacity=it.dead?Math.max(0,1-it.fade):1}}
};
let Scene=SceneSVG;
function pickScene(){Scene=(S.view!=='2d'&&THREE_OK())?SceneThree:SceneSVG}
const STATECOL={idea:'#9aa3a0',drafted:'#6a5acd',rendered:'#3b82f6',in_review:'#f0a81c',approved:'#22a35a',scheduled:'#14b8a6',published:'#facc15',measured:'#0d9488',archived:'#94a3b8'};
function cartridge(){return `<g><circle class="gold pulse-g" r="30" fill="#ffe27a" opacity=".55" style="display:none"/><rect class="body" x="-14" y="-19" width="28" height="38" rx="6" fill="#999" stroke="#10201a" stroke-width="2.4"/><rect x="-9" y="-12" width="18" height="12" rx="2" fill="#fff" opacity=".9"/><circle cx="-6" cy="9" r="2.2" fill="#10201a"/><circle cx="6" cy="9" r="2.2" fill="#10201a"/><path class="crack" d="M-12 -18L-2 -4 -9 4 2 19" stroke="#fff" stroke-width="2.4" fill="none" style="display:none"/></g>`}
function geoInit(){const ns='http://www.w3.org/2000/svg',s=document.createElementNS(ns,'svg');s.setAttribute('width','0');s.setAttribute('height','0');s.style.cssText='position:absolute;visibility:hidden';document.body.appendChild(s);
  for(const v of ['landscape','portrait']){const p=document.createElementNS(ns,'path');p.setAttribute('d',GEO[v].path);s.appendChild(p);const len=p.getTotalLength();SIM.len=SIM.len||{};SIM.len[v]=len;
    const arr=[0];STAGES.forEach(st=>{const [x,y]=GEO[v].st[st];let best=0,bd=1e9;for(let l=0;l<len;l+=3){const q=p.getPointAtLength(l),d=(q.x-x)**2+(q.y-y)**2;if(d<bd){bd=d;best=l}}arr.push(best/len)});arr.push(1);SIM.anchors[v]=arr}
  geo3();s.remove()}

/* ---------- toast, copy, badges ---------- */
let toastT;function toast(m){let box=$('.toast',$('#frame'));if(box)box.remove();box=document.createElement('div');box.className='toast';box.innerHTML=`<div>${esc(m)}</div>`;$('#frame').appendChild(box);clearTimeout(toastT);toastT=setTimeout(()=>box.remove(),2200)}
function copy(txt){try{navigator.clipboard.writeText(txt).then(()=>toast(t('copied')),()=>toast(txt))}catch(e){toast(txt)}}
const needCount=()=>S.queue.length+S.pubq.length+S.fails.length;

/* ---------- pages ---------- */
const P={};
const poster=(it,small)=>{const cap=(it.hook||'').split(' ').slice(0,3).join(' ');return `<div class="phone" ${small?'style="width:100%;border-width:3px;border-radius:12px"':''}><div class="poster" style="background:${posterBg(it.n)}"><h5>${esc(it.hook||'')}</h5><span class="cap">${esc(cap)}</span><span class="cta">${t('poster.cta')}</span></div><div class="play"><span>${ico('play')}</span></div><div class="bar"><i></i></div></div>`};
const empty=(k)=>`<div class="empty"><b>${t(k+'.title')}</b>${t(k+'.sub')}</div>`;
const field=(id,label,val,o={})=>`<div class="field ${o.err?'err':''}"><label for="${id}">${label}</label>${o.area?`<textarea id="${id}" ${o.ph?`placeholder="${esc(o.ph)}"`:''}>${esc(val)}</textarea>`:`<input id="${id}" type="${o.type||'text'}" value="${esc(val)}" ${o.ro?'readonly':''} ${o.ph?`placeholder="${esc(o.ph)}"`:''}>`}${o.help?`<div class="help">${o.help}</div>`:''}${o.cnt?`<div class="cnt">${o.cnt}</div>`:''}</div>`;
const select=(id,label,opts,sel,help)=>`<div class="field"><label for="${id}">${label}</label><select id="${id}">${opts.map(([v,l])=>`<option value="${v}" ${v===sel?'selected':''}>${esc(l)}</option>`).join('')}</select>${help?`<div class="help">${help}</div>`:''}</div>`;
const chips=(arr,cls='')=>`<div class="chips">${arr.map(a=>`<span class="chip x ${cls}">${esc(a)} <button class="rm" aria-label="remove">×</button></span>`).join('')}</div>`;
const sw=(label,checked,id)=>`<label class="row" style="justify-content:space-between;gap:12px"><span>${label}</span><span class="switch"><input type="checkbox" ${id?`id="${id}"`:''} ${checked?'checked':''}><span></span></span></label>`;
const code=(txt)=>`<div class="code">${esc(txt)}<button class="cp" data-copy="${esc(txt.split('\n')[0])}">${t('copy')}</button></div>`;
const banner=(kind,ic,title,body)=>`<div class="banner ${kind}">${ico(ic)}<div><b>${title}</b><p>${body}</p></div></div>`;
const head=(k,right='')=>`<div class="head"><div><h3>${t(k+'.h')}</h3><p>${t(k+'.p')}</p></div>${right}</div>`;

P.login=()=>`<div class="login">${heroImg()?`<img class="loginhero" src="${heroImg()}" alt="">`:''}<div class="logo">${LOGO}<span>Simplicio</span></div><div class="stack tight"><h3 style="font-size:26px">${t('login.h')}</h3><p style="color:var(--muted)">${t('login.p')}</p></div>
<div class="card stack"><div class="field ${S.loginErr?'err':''}"><label for="otp">${t('login.code')}</label><input id="otp" class="otp inp" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" placeholder="123-456" value="${esc(S.otp)}"><div class="help">${S.loginErr?t('login.err'):t('login.help')}</div></div><button class="btn primary" data-act="login">${t('login.open')}</button></div>
<div class="stack tight"><div class="lbl">${t('login.where')}</div>${code('simplicio-video up\n  panel       http://127.0.0.1:8787\n  login code  482-913')}</div>
<p class="row" style="color:var(--muted);font-size:12.5px"><span class="chip good">${t('login.local')}</span>${t('login.agents')}</p></div>`;

P.factory=()=>Twin.html()+`<div class="under"><div class="card"><h4>${t('feed.h')} <small>${t('feed.live')}</small></h4><div id="feed"></div></div>
<div class="card"><h4>${t('stats.h')}</h4><div class="stat"><div><b id="stCycle">1</b><span>${t('stats.cycle')}</span></div><div><b id="stDone">0</b><span>${t('stats.posted')}</span></div><div><b>0</b><span>${t('stats.tokens')}</span></div><div><b>0</b><span>${t('stats.credits')}</span></div></div>
<p style="margin-top:12px;color:var(--muted);font-size:12.5px">${t('stats.note')}</p><div class="row" style="margin-top:10px"><button class="btn sm danger" data-act="fail">${t('stats.fail')}</button><span class="chip">${t('theme.cur')}: ${esc(TCUR().name[LG()])}</span></div></div></div>`;

const evRow=ev=>{const role=ev.stage?STAGE_ROLE[ev.stage]:null;return `<div class="ev"><time>${fmtT(ev.ts)}</time><div><span class="who" style="color:${ev.stage?SC[ev.stage]:'var(--muted)'}">${esc(role?charName(role):t('actor.system'))}</span> ${esc(phrase(ev))}</div><span class="k">${ev.kind}</span></div>`};
P.inbox=()=>{const n=needCount(),items=[];
  if(S.queue.length)items.push(`<div class="need gate"><div class="ic">${ico('review')}</div><div><h4>${t('inbox.review',{n:S.queue.length})}</h4><p>${t('inbox.review.p')}</p></div><button class="btn primary" data-go="review">${t('nav.review')}</button></div>`);
  if(S.pubq.length)items.push(`<div class="need gate"><div class="ic">${ico('publish')}</div><div><h4>${t('inbox.pub',{n:S.pubq.length})}</h4><p>${t('inbox.pub.p')}</p></div><button class="btn primary" data-go="publish">${t('nav.publish')}</button></div>`);
  S.fails.forEach(f=>items.push(`<div class="need fail"><div class="ic">${ico('fail')}</div><div><h4>${t('inbox.fail')}</h4><p>${esc(f.hook)} · ${f.id}</p></div><div class="row"><button class="btn sm" data-act="retry" data-id="${f.id}">${t('retry')}</button><button class="btn sm ghost" data-act="skip" data-id="${f.id}">${t('skip')}</button></div></div>`));
  items.push(`<div class="need"><div class="ic">${ico('info')}</div><div><h4>${t('inbox.budget')}</h4><p>${t('inbox.budget.p')}</p></div><button class="btn sm" data-go="settings" data-tab="policy">${t('nav.settings')}</button></div>`);
  return `${head('inbox')}<div class="inbox">${n?'':empty('inbox.empty')}${items.join('')}</div>`};

P.brand=()=>{const L=LG();return `${head('brand')}
<div class="cols c21"><div class="stack">
<div class="card"><h4>${t('brand.create')} <span class="tag-tokens">0 ${t('tokens')}</span></h4><div class="fields"><div class="field"><label for="url">${t('brand.url')}</label><input id="url" type="url" value="https://acme-coffee.example" placeholder="https://"><div class="help">${t('brand.url.help')}</div></div></div>
<details style="margin-top:10px"><summary style="cursor:pointer;color:var(--muted);font-weight:600">${t('brand.adv')}</summary><div class="fields" style="margin-top:10px">${field('offl',t('brand.offline'),'',{ph:'~/sites/acme-coffee/',help:t('brand.offline.help')})}</div></details>
<div class="row" style="margin-top:14px"><button class="btn primary" data-act="read">${t('brand.read')}</button><span class="chip good">${ico('check','width="13" height="13"')}${t('brand.read.done')}</span></div>
<ul style="margin:12px 0 0;padding-inline-start:18px;color:var(--muted);font-size:12.5px"><li>${t('brand.p1')}</li><li>${t('brand.p2')}</li><li>${t('brand.p3')}</li></ul></div>
<div class="card"><h4>${t('brand.identity')}</h4><div class="fields two">${field('bn',t('brand.name'),'Acme Coffee')}${field('bs',t('brand.slug'),'acme-coffee',{ro:1})}
${select('bl',t('brand.lang'),[['pt-BR','Português (Brasil)'],['en','English'],['es-MX','Español (México)']],S.lang==='en'?'en':'pt-BR',t('brand.lang.help'))}${select('bz',t('brand.tz'),[['America/Sao_Paulo','America/Sao_Paulo (UTC−03)'],['Europe/Lisbon','Europe/Lisbon'],['America/New_York','America/New_York']],'America/Sao_Paulo',t('brand.tz.help'))}</div></div>
<div class="card"><h4>${t('brand.product')}</h4><div class="fields">${field('bsum',t('brand.summary'),L==='pt'?'Cafés especiais torrados toda semana, enviados para todo o Brasil.':'Specialty coffee roasted every week and shipped nationwide.',{area:1})}</div>
<div class="lbl" style="margin:12px 0 6px">${t('brand.offers')}</div>
<div class="fields three"><div class="field"><label>${t('brand.offer.name')}</label><input class="inp" type="text" value="${L==='pt'?'Assinatura mensal':'Monthly subscription'}"></div><div class="field"><label>${t('brand.offer.price')}</label><input class="inp" type="number" value="${L==='pt'?'64.9':'12.9'}"></div>${select('cur',t('brand.offer.cur'),[['BRL','BRL'],['USD','USD'],['EUR','EUR']],L==='pt'?'BRL':'USD')}</div>
<button class="btn sm" style="margin-top:10px">+ ${t('brand.offer.add')}</button></div>
<div class="card"><h4>${t('brand.audience')}</h4><div class="stack tight"><div class="lbl">${t('brand.segments')}</div>${chips(L==='pt'?['Quem ama espresso em casa','Presentes para cafeteiros']:['Home espresso lovers','Gifts for coffee fans'])}<div class="lbl" style="margin-top:6px">${t('brand.tone')}</div>${chips(L==='pt'?['caloroso','direto','curioso']:['warm','direct','curious'],'acc')}
<div class="fields two" style="margin-top:6px">${field('do',t('brand.do'),L==='pt'?'Falar de sabor e preparo':'Talk about flavor and brewing',{area:1})}${field('dont',t('brand.dont'),L==='pt'?'Prometer cura ou milagres':'Promise cures or miracles',{area:1})}</div></div></div>
<div class="card"><h4>${t('brand.visual')}</h4><div class="row" style="gap:14px"><div class="row" style="gap:8px">${['#3a2418','#c98b4a','#f5efe6'].map((c,i)=>`<label class="row" style="gap:6px"><span style="width:28px;height:28px;border-radius:6px;background:${c};border:1px solid var(--line-strong);display:inline-block"></span><input class="inp mono" style="width:96px;min-height:32px" type="text" value="${c}" aria-label="color ${i+1}"></label>`).join('')}</div><div class="row"><span style="width:56px;height:56px;border-radius:10px;border:1px dashed var(--line-strong);display:grid;place-items:center;color:var(--faint);font-size:11px">logo</span><button class="btn sm">${t('brand.logo')}</button></div></div></div>
<div class="card"><h4>${t('brand.claims')}</h4><div class="stack tight"><div class="lbl">${t('brand.forbidden')}</div>${chips(L==='pt'?['cura','resultado garantido','antes e depois']:['cure','guaranteed results','before and after'],'bad')}<div class="fields two" style="margin-top:6px">${field('disc',t('brand.disclaimers'),'',{area:1,ph:t('brand.disclaimers.ph')})}${select('reg',t('brand.regulated'),[['none',t('reg.none')],['health',t('reg.health')],['finance',t('reg.finance')],['legal',t('reg.legal')]],'none',t('brand.regulated.help'))}</div></div></div>
</div><div class="stack"><div class="card"><h4>${t('brand.facts')} <small>${FACTS.filter(f=>f.v).length}/${FACTS.length} ${t('verified')}</small></h4><div class="table">${FACTS.map(f=>`<div class="tr"><div style="min-width:0"><b>${f.id}</b> ${esc(f[LG()==='pt'?'pt':'en'])}<div class="mono" style="font-size:11.5px;color:var(--faint)">${f.src?'acme-coffee.example'+f.src+' · 2026-10-06 · sha 3f9a…':t('brand.user')}</div></div><div class="row"><span class="chip ${f.origin==='user'?'info':''}">${t('origin.'+f.origin)}</span><label class="switch"><input type="checkbox" ${f.v?'checked':''} aria-label="${t('verified')}"><span></span></label></div></div>`).join('')}</div><button class="btn sm" style="margin-top:12px" data-act="confirmall">${t('brand.confirmall')}</button><p class="help" style="margin-top:8px;color:var(--faint);font-size:12px">${t('brand.facts.help')}</p></div>
<div class="card"><h4>${t('brand.competitors')}</h4><div class="fields two">${field('c1',t('brand.offer.name'),'Beta Roasters')}${field('c1u','URL','https://beta-roasters.example',{type:'url'})}</div><p style="font-size:12px;color:var(--faint);margin-top:8px">${t('brand.competitors.help')}</p></div></div></div>`};

P.ideas=()=>{const L=LG(),rows=HOOKS[S.lang].map((h,i)=>`<div class="li" style="grid-template-columns:minmax(0,1fr) auto"><div style="min-width:0"><b>${esc(h)}</b><div class="row" style="margin-top:5px;gap:6px"><span class="chip acc">${t('fam.'+FAM[i])}</span><span class="chip ${i<3?'good':''}">${i<3?t('ideas.hint',{s:[.82,.74,.69][i],n:[6,5,4][i]}):t('ideas.prior')}</span><span class="chip good">${ico('check','width="12" height="12"')}${t('ideas.guard',{f:['F3, F4','F2','F1','F5','F2'][i]})}</span></div></div><div class="row"><button class="btn sm primary" data-act="pick" data-i="${i}">${t('ideas.pick')}</button><button class="btn sm ghost">${t('ideas.discard')}</button></div></div>`).join('');
  return `${head('ideas',`<span class="tag-tokens">0 ${t('tokens')} · ${t('ideas.rules')}</span>`)}
<div class="card" style="margin-bottom:14px"><div class="row sp"><div class="row"><div class="field" style="width:130px"><label for="nn">${t('ideas.howmany')}</label><input id="nn" type="number" min="1" max="10" value="${S.idea.n}"></div><button class="btn primary" style="align-self:end" data-act="gen">${t('ideas.generate')}</button></div><button class="btn" data-act="addidea">+ ${t('ideas.add')}</button></div>
${S.idea.adding?`<div class="fields two" style="margin-top:14px">${field('ih',t('ideas.hook'),L==='pt'?'Frete grátis por R$ 9,90':'Free shipping for $2.99',{area:1,err:1,cnt:'28/90',help:t('ideas.blocked')})}<div class="stack tight">${select('ia',t('ideas.angle'),[['benefit',t('angle.benefit')],['question',t('angle.question')],['story',t('angle.story')],['proof',t('angle.proof')],['offer',t('angle.offer')]],'offer')}${select('if',t('ideas.family'),FAM.map(f=>[f,t('fam.'+f)]),'offer')}<div class="banner bad">${ico('alert')}<div><b>${t('ideas.guard.bad')}</b><p>${t('ideas.guard.bad.p')}</p></div></div></div></div>`:''}</div>
<div class="card"><div class="list">${rows}</div></div>`};

P.studio=()=>{const it=S.queue[0]||S.pubq[0]||{hook:HOOKS[S.lang][0],n:1,id:'itm_01'},L=LG(),st=S.studio;
  return `${head('studio',`<span class="chip ${st.rendered?'good':'info'}">${t(st.rendered?'state.rendered':'state.drafted')}</span>`)}
<div class="cols c21"><div class="stack"><div class="card"><h4>${t('studio.draft')}</h4><div class="fields">${field('sh',t('ideas.hook'),it.hook,{area:1})}<div class="fields two">${select('sa',t('ideas.angle'),[['benefit',t('angle.benefit')],['question',t('angle.question')],['offer',t('angle.offer')]],'question')}${select('stp',t('studio.template'),[['brand-promo','brand-promo (ready)'],['saude-odontologia','saude-odontologia (ready)'],['assistencia-tecnica-games','assistencia-tecnica-games (ready)']],'brand-promo')}</div>
<div class="fields two">${select('spr',t('studio.preset'),[['9:16-15',t('preset.vertical')],['1:1-20',t('preset.square')]],'9:16-15')}<div class="field"><label for="sd">${t('studio.duration')}: <span id="sdv">15</span> s</label><input id="sd" class="range" type="range" min="8" max="20" value="15"></div></div></div>
<div class="lbl" style="margin:14px 0 6px">${t('studio.scenes')}</div><div class="list">${[[L==='pt'?'Você erra aqui ao escolher o moedor?':'Are you making this mistake?','F3'],[L==='pt'?'Torrado toda semana, em pequenos lotes':'Roasted weekly in small batches','F2'],[L==='pt'?'Frete grátis acima de R$ 150':'Free shipping over $50','F1']].map((s,i)=>`<div class="li" style="grid-template-columns:auto minmax(0,1fr) auto"><span class="chip">${i+1}</span><input class="inp" type="text" value="${esc(s[0])}"><span class="chip good" title="${t('studio.fact')}">${s[1]}</span></div>`).join('')}</div></div>
<div class="card"><h4>${t('studio.audio')}</h4><div class="fields two">${select('sv',t('studio.voice'),[['none',t('voice.none')],['local','Kokoro ('+t('voice.local')+')'],['gemini','Gemini TTS ('+t('voice.cloud')+')'],['voxcpm','VoxCPM2 ('+t('voice.local')+')']],'none',t('studio.voice.help'))}${select('sm',t('studio.music'),[['engine',t('music.engine')],['none',t('music.none')]],'engine')}</div><div class="stack tight" style="margin-top:10px">${sw(t('studio.captions'),true)}${sw(t('studio.cta')+': <b>'+t('poster.cta')+'</b>',true)}</div></div>
<div class="card"><h4>${t('studio.route')}</h4><div class="stack tight"><label class="radio"><input type="radio" name="route" ${S.route==='det'?'checked':''} data-act="route" data-v="det"><div><b>${t('route.det')}</b><span>${t('route.det.p')}</span></div></label><label class="radio"><input type="radio" name="route" ${S.route==='ai'?'checked':''} data-act="route" data-v="ai"><div><b>${t('route.ai')}</b><span>${t('route.ai.p')}</span></div></label>
${S.route==='ai'?`<div class="stack tight" style="padding-inline-start:12px"><label class="check"><input type="checkbox" checked><div><b>${t('step.caption')}</b><span>${t('step.caption.p')}</span></div></label><label class="check"><input type="checkbox"><div><b>${t('step.cover')}</b><span>${t('step.cover.p')}</span></div></label><label class="check"><input type="checkbox"><div><b>${t('step.dub')}</b><span>${t('step.dub.p')}</span></div></label><label class="check"><input type="checkbox"><div><b>${t('step.media')}</b><span>${t('step.media.p')}</span></div></label>${banner('info','info',t('route.budget'),t('route.budget.p'))}</div>`:''}</div></div></div>
<div class="stack"><div class="card" style="text-align:center">${poster(it)}<div class="stack tight" style="margin-top:14px;text-align:start">${st.rendering?`<div class="meter"><i style="width:60%"></i></div><p class="help" style="color:var(--muted)">${t('studio.rendering')}</p>`:st.rendered?`<dl class="kv"><dt>${t('studio.time')}</dt><dd>9.4 s</dd><dt>${t('studio.hash')}</dt><dd class="mono">3f9a…c21e</dd><dt>${t('stats.tokens')}</dt><dd>0</dd><dt>${t('stats.credits')}</dt><dd>0</dd></dl>`:`<p style="color:var(--muted);font-size:12.5px">${t('studio.notrendered')}</p>`}
<button class="btn primary" data-act="render">${t('studio.render')}</button>${st.rendered?`<button class="btn" data-go="review">${t('studio.send')}</button>`:''}</div></div></div></div>`};

P.review=()=>{const q=S.queue;if(!q.length)return `${head('review')}${empty('review.empty')}`;const it=q[Math.min(S.rv,q.length-1)];
  return `${head('review',`<span class="chip">${q.length} ${t('review.waiting')}</span>`)}
${S.stale?banner('warn','alert',t('review.stale'),t('review.stale.p')):''}
<div class="cols c12" style="margin-top:${S.stale?'12px':'0'}"><div class="stack"><div class="card" style="text-align:center">${poster(it)}<div class="thumbs" style="margin-top:12px;justify-content:center">${q.map((x,i)=>`<button data-act="rv" data-i="${i}" aria-current="${i===S.rv}" aria-label="${esc(x.hook)}"><span style="display:block;height:100%;background:${posterBg(x.n)}"></span></button>`).join('')}</div></div>
<div class="card"><dl class="kv"><dt>${t('review.item')}</dt><dd class="mono">${it.id}</dd><dt>${t('studio.hash')}</dt><dd class="mono">${it.hash.slice(0,4)}…${it.hash.slice(-4)}</dd><dt>${t('studio.template')}</dt><dd>brand-promo</dd><dt>${t('studio.duration')}</dt><dd>15 s · 9:16</dd><dt>${t('review.cost')}</dt><dd>0 ${t('tokens')} · 0 ${t('credits')}</dd></dl></div></div>
<div class="stack"><div class="card"><h4>${t('review.checklist')}</h4><label class="check"><input type="checkbox" id="ck1"><div><b>${t('ck.ai')}</b><span>${t('ck.ai.p')}</span></div></label><label class="check"><input type="checkbox" id="ck2"><div><b>${t('ck.music')}</b><span>${t('ck.music.p')}</span></div></label><label class="check"><input type="checkbox" id="ck3"><div><b>${t('ck.claims')}</b><span>${t('ck.claims.p')}</span></div></label></div>
<div class="card"><h4>${t('review.decision')}</h4><div class="fields"><div class="fields two">${select('rr',t('review.reason'),[['',t('reason.none')],['hook_weak',t('reason.hook_weak')],['off_brand',t('reason.off_brand')],['compliance',t('reason.compliance')],['quality',t('reason.quality')],['other',t('reason.other')]],'')}<div></div></div>${field('rn',t('review.note'),'',{area:1,ph:t('review.note.ph')})}</div>
<div class="row" style="margin-top:14px"><button class="btn primary" id="btnApprove" data-act="approve" disabled>${t('review.approve')} <span class="kbd">A</span></button><button class="btn" data-act="changes">${t('review.changes')} <span class="kbd">N</span></button><button class="btn danger" data-act="discard">${t('review.discard')} <span class="kbd">D</span></button></div>
<p class="help" style="margin-top:10px;color:var(--faint);font-size:12px">${t('review.bound')} <a href="#" data-act="stale">${t('review.stale.demo')}</a></p></div></div></div>`};

P.publish=()=>{const p=S.pubq[0],L=LG();
  const upload=S.canUpload?banner('good','check',t('pub.upload.ok'),t('pub.upload.ok.p')):banner('warn','alert',t('pub.upload.no'),t('pub.upload.no.p'));
  if(!p)return `${head('publish')}${upload}<div style="margin-top:12px">${empty('pub.empty')}</div>`;
  return `${head('publish',`<span class="chip good">${ico('check','width="13" height="13"')}Real Oficial · ${t('pub.connected')}</span>`)}${upload}
<div class="cols c21" style="margin-top:12px"><div class="stack">
<div class="card"><div class="step"><span class="n done">1</span><div><h4 style="margin-bottom:8px">${t('pub.dest')}</h4>${ACCTS.map((a,i)=>`<div class="acct"><span class="pf" style="background:${a.c}">${a.pf}</span><div style="min-width:0"><b>${a.name}</b> <span class="mono" style="color:var(--muted);font-size:12px">${a.h}</span><div style="font-size:12px;color:var(--faint)">${t('pub.today',{u:a.used,m:3})}</div></div><label class="row" style="gap:8px"><span class="chip ${a.ok?'good':'warn'}">${a.ok?t('pub.healthy'):t('pub.reconnect')}</span><span class="switch"><input type="checkbox" ${i<2?'checked':''} ${a.ok?'':'disabled'} aria-label="${a.name}"><span></span></span></label></div>`).join('')}</div></div></div>
<div class="card"><div class="step"><span class="n done">2</span><div style="min-width:0"><h4 style="margin-bottom:8px">${t('pub.when')}</h4><div class="fields two">${field('pw',t('pub.when.f'),'2026-10-13T18:00',{type:'datetime-local',help:t('pub.when.help')})}<div class="field"><label>${t('pub.slot')}</label><button class="btn" data-act="slot">${t('pub.slot.use')}</button></div></div></div></div></div>
<div class="card"><div class="step"><span class="n done">3</span><div style="min-width:0"><h4 style="margin-bottom:8px">${t('pub.caption')}</h4><div class="fields">${field('pc',t('pub.caption.f'),(L==='pt'?'Seu café da manhã merece mais. Frete grátis acima de R$ 150.':'Your morning deserves more. Free shipping over $50.'),{area:1,cnt:'61 / 150'})}</div><div class="chips" style="margin:8px 0">${['#coffee','#espresso','#acmecoffee'].map(h=>`<span class="chip acc">${h}</span>`).join('')}</div><div class="row"><button class="btn sm">${t('pub.caption.def')} <span class="tag-tokens">0 ${t('tokens')}</span></button><button class="btn sm">${t('pub.caption.ro')}</button></div></div></div></div>
<div class="card"><div class="step"><span class="n done">4</span><div style="min-width:0"><h4 style="margin-bottom:8px">${t('pub.flags')}</h4><div class="stack tight">${sw(t('pub.ai'),false)}${sw(t('pub.ad'),true)}</div></div></div></div></div>
<div class="stack"><div class="card"><h4>${t('pub.dry')} <span class="chip info">${t('pub.dry.tag')}</span></h4><dl class="kv"><dt>${t('review.item')}</dt><dd class="mono">${p.id}</dd><dt>${t('pub.payload')}</dt><dd class="mono">${p.hash.slice(0,4)}…${p.hash.slice(-4)}</dd><dt>${t('pub.dest')}</dt><dd>TikTok, Instagram Reels</dd><dt>${t('pub.expires')}</dt><dd>14:32</dd></dl>
<div class="stack tight" style="margin-top:10px">${banner('info','info',t('pub.warn.h'),t('pub.warn.p'))}</div></div>
<div class="card"><h4>${t('pub.confirm')}</h4><p style="color:var(--muted);font-size:13px;margin-bottom:12px">${t('pub.confirm.p')}</p><button class="btn primary hold" id="holdBtn" ${S.canUpload?'':'disabled'}><i></i><span>${ico('lock','width="16" height="16"')} ${t('pub.hold')}</span></button>
${S.canUpload?'':`<p style="font-size:12px;color:var(--warn);margin-top:8px">${t('pub.hold.off')}</p><button class="btn" style="margin-top:10px;width:100%" data-act="export">${t('pub.export')}</button>`}
<p style="font-size:12px;color:var(--faint);margin-top:10px">${t('pub.agents')}</p></div></div></div>`};

P.activity=()=>`${head('activity')}<div class="card"><div class="chips" style="margin-bottom:10px">${['all','stage','gate','publish','error'].map((f,i)=>`<span class="chip ${i===0?'acc':''}">${t('flt.'+f)}</span>`).join('')}</div><div id="actList">${S.events.map(evRow).join('')||empty('act.empty')}</div></div>`;

const tabs=['appearance','policy','plugins','health','updates','workspace'];
P.settings=()=>{let b='';
  if(S.tab==='appearance')b=`<div class="stack"><div class="card"><h4>${t('set.scenario')} <small>${t('set.scenario.p')}</small></h4><div class="themes">${THEME_ORDER.map(id=>{const th=TH[id];return `<button class="tcard" data-act="theme" data-id="${id}" aria-pressed="${S.theme===id}"><span class="mini">${id==='br'&&heroImg()?`<img src="${heroImg()}" alt="">`:sceneSVG(th,'landscape',{mini:true,uid:'g'+id})}</span><b>${th.name[LG()]} <span class="chip ${th.status==='mvp'?'good':''}">${t(th.status==='mvp'?'theme.mvp':'theme.concept')}</span></b><small>${th.tag[LG()]}</small></button>`}).join('')}</div>
<p style="margin-top:12px;font-size:12.5px;color:var(--muted)">${t('theme.ip')}</p></div>
<div class="cols c2"><div class="card"><h4>${t('set.lang')}</h4><div class="fields">${select('ul',t('set.ui'),[['en','English'],['pt-BR','Português (Brasil)']],S.lang,t('set.ui.help'))}${sw(t('set.rtl'),S.rtl,'rtlSw')}${sw(t('set.reduce'),S.reduce,'redSw')}</div></div>
<div class="card"><h4>${t('set.custom')}</h4><p style="color:var(--muted);font-size:13px;margin-bottom:10px">${t('set.custom.p')}</p>${code('simplicio-video theme new my-theme\nsimplicio-video theme validate ./my-theme\nsimplicio-video theme use my-theme')}<div class="code" style="margin-top:8px;color:#9fc7b3">themes/my-theme/\n  theme.json\n  assets/*.svg\n  locales/pt-BR.json</div></div></div></div>`;
  else if(S.tab==='policy')b=`<div class="cols c2"><div class="stack"><div class="card"><h4>${t('pol.autonomy')}</h4><div class="stack tight">${[['L0','pol.l0'],['L1','pol.l1'],['L2','pol.l2'],['L3','pol.l3']].map(([k,l])=>`<label class="radio" ${k==='L3'?'aria-disabled="true"':''}><input type="radio" name="aut" ${k==='L1'?'checked':''} ${k==='L3'?'disabled':''}><div><b>${k} · ${t(l)}</b><span>${t(l+'.p')}</span></div></label>`).join('')}</div></div>
<div class="card"><h4>${t('pol.kill')}</h4><p style="color:var(--muted);font-size:13px;margin-bottom:10px">${t('pol.kill.p')}</p><button class="btn danger" data-act="stop">${t('pol.kill.btn')}</button></div></div>
<div class="card"><h4>${t('pol.budgets')} <small>${t('pol.perday')}</small></h4><div class="fields two">${[['bt',t('pol.tokens'),0],['bu',t('pol.usd'),0],['bc',t('pol.credits'),0],['br',t('pol.renders'),40],['bp',t('pol.posts'),3],['bm',t('pol.inflight'),10]].map(([i,l,v])=>field(i,l,v,{type:'number'})).join('')}</div><div class="fields two" style="margin-top:12px">${field('q1',t('pol.quiet.from'),'23:00',{type:'time'})}${field('q2',t('pol.quiet.to'),'07:00',{type:'time'})}</div><p style="margin-top:10px;font-size:12.5px;color:var(--muted)">${t('pol.zero')}</p></div></div>`;
  else if(S.tab==='plugins')b=`<div class="card"><h4>${t('plug.h')} <small>${t('plug.p')}</small></h4><div class="table">${PLUGINS.map(([id,kind,status,perm])=>`<div class="tr plug"><div><b>${id}</b></div><div><span class="chip">${kind}</span></div><div class="chips">${perm.length?perm.map(x=>`<span class="chip ${x.startsWith('can_')?'warn':''}">${x}</span>`).join(''):`<span class="chip">${t('plug.noperm')}</span>`}</div><label class="switch"><input type="checkbox" checked aria-label="${id}"><span></span></label></div>`).join('')}</div><p style="margin-top:10px;font-size:12.5px;color:var(--muted)">${t('plug.note')}</p></div>`;
  else if(S.tab==='health'){const rows=[['ok','Python','3.12.4'],['ok','Node','22.9.0'],['ok','ffmpeg','7.1 · libass'],['warn',t('doc.disk'),'8.2 GB'],['ok',t('doc.port'),'8787'],['ok',t('doc.plugins'),'10'],['bad','Real Oficial',t('doc.ro')]];
    b=`<div class="card"><h4>${t('doc.h')} <button class="btn sm" data-act="doctor">${S.doc.running?t('doc.running'):t('doc.run')}</button></h4><div class="list">${rows.map(([k,n,v])=>`<div class="li" style="grid-template-columns:auto minmax(0,1fr) auto"><span class="chip ${k==='ok'?'good':k==='warn'?'warn':'bad'}">${k==='ok'?'OK':k==='warn'?'!':'×'}</span><div><b>${n}</b> <span style="color:var(--muted)">${v}</span>${k==='warn'?`<div class="mono" style="font-size:12px;color:var(--faint)">${t('doc.fix')}: simplicio-video clean --dry-run</div>`:k==='bad'?`<div class="mono" style="font-size:12px;color:var(--faint)">${t('doc.fix')}: simplicio-video setup</div>`:''}</div><span></span></div>`).join('')}</div></div>`}
  else if(S.tab==='updates')b=`<div class="cols c2"><div class="card"><h4>${t('upd.h')}</h4><dl class="kv"><dt>${t('upd.ver')}</dt><dd class="mono">v0.4.0 (MVP)</dd><dt>${t('upd.theme')}</dt><dd>${TCUR().name[LG()]}</dd></dl><div class="row" style="margin-top:12px"><button class="btn primary" data-act="upd">${t('upd.check')}</button></div>${S.upd?`<div style="margin-top:12px">${banner('info','info',t('upd.found'),t('upd.found.p'))}</div>`:''}</div>
<div class="card"><h4>${t('upd.cmd')}</h4>${code('simplicio-video update --check\nsimplicio-video update')}<p style="margin-top:10px;font-size:12.5px;color:var(--muted)">${t('upd.p')}</p>${code('git checkout <previous-commit>   # roll back')}</div></div>`;
  else b=`<div class="cols c2"><div class="card"><h4>${t('ws.h')}</h4><dl class="kv"><dt>${t('ws.path')}</dt><dd class="mono">~/.simplicio-video/workspaces/default</dd><dt>${t('ws.layout')}</dt><dd class="mono">factory/v1</dd></dl>${[['events',22,'1.2 GB'],['previews',46,'3.8 GB'],['logs',15,'0.1 GB']].map(([k,v,s])=>`<div style="margin-top:10px"><div class="row sp"><span>${t('ws.'+k)}</span><span class="mono" style="font-size:12px;color:var(--muted)">${s}</span></div><div class="meter"><i style="width:${v}%"></i></div></div>`).join('')}</div>
<div class="card"><h4>${t('ws.retention')}</h4><ul style="margin:0 0 12px;padding-inline-start:18px;color:var(--muted);font-size:13px"><li>${t('ws.r1')}</li><li>${t('ws.r2')}</li><li>${t('ws.r3')}</li></ul><button class="btn" data-act="clean">${t('ws.clean')}</button>${S.clean?`<div style="margin-top:10px">${code('simplicio-video clean --dry-run\n  would remove 3.1 GB  (previews older than 14 days)\n  nothing was deleted')}</div>`:''}</div></div>`;
  return `${head('settings')}<div class="tabsx" role="tablist">${tabs.map(k=>`<button role="tab" data-act="tab" data-v="${k}" aria-current="${S.tab===k}">${t('tab.'+k)}</button>`).join('')}</div>${b}`};

/* ---------- shell, routing, refresh ---------- */
function rail(){return PAGES.map(k=>`<button class="nav" title="${t('nav.'+k)}" aria-label="${t('nav.'+k)}" data-go="${k}" aria-current="${S.page===k?'page':'false'}">${ico(k==='inbox'?'inbox':k)}<span>${t('nav.'+k)}</span>${k==='inbox'&&needCount()?`<span class="badge">${needCount()}</span>`:''}</button>`).join('')}
function tabbar(){return TABS_MOBILE.map(k=>{const cur=k==='more'?(!TABS_MOBILE.includes(S.page)&&S.page!=='login'):S.page===k;return `<button class="tab" data-go="${k}" aria-current="${cur?'page':'false'}">${ico(k==='inbox'?'inbox':k)}<span>${t('nav.'+k)}</span>${k==='inbox'&&needCount()?`<span class="dot">${needCount()}</span>`:''}</button>`}).join('')}
function sheet(){return `<div class="sheet" data-act="closesheet"><div class="sheet-in">${['brand','ideas','studio','activity','settings'].map(k=>`<button data-go="${k}" aria-current="${S.page===k?'page':'false'}">${ico(k)}${t('nav.'+k)}</button>`).join('')}</div></div>`}
function applyTheme(){const th=TCUR(),a=$('#app');a.dir=S.rtl?'rtl':'ltr';$('#frame').dataset.device=S.device;$('#frame').dataset.full=S.full?'1':'0';document.documentElement.lang=S.lang;a.classList.toggle('reduce',S.reduce)}
function renderShell(){const logged=S.page!=='login';$('#app').dataset.rail=S.rail?'min':'full';
  $('#rail').innerHTML=logged?`<div class="railhead"><div class="logo">${LOGO}<span>Simplicio</span></div><button class="railtoggle" data-act="rail" aria-expanded="${!S.rail}" aria-label="${t(S.rail?'rail.expand':'rail.collapse')}" title="${t(S.rail?'rail.expand':'rail.collapse')}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg></button></div>${rail()}<div class="spacer"></div><div class="foot"><div><b>Acme Coffee</b> · ${TCUR().name[LG()]}</div><div class="mono">v0.4.0 MVP</div></div>`:'';
  $('#tabs').innerHTML=logged?tabbar():'';$('#tabs').style.display=logged?'':'none';
  $('#ttl').textContent=t('nav.'+(S.page==='login'?'factory':S.page));$('#topLogo').style.display=logged?'':'';
  const nb=$('#needTop');nb.hidden=!logged||!needCount();nb.textContent=needCount()+' · '+t('nav.inbox');
  $('#sheetHost').innerHTML=S.more?sheet():''}
function renderPage(){Twin.unmount();$('#main').dataset.page=S.page;SceneSVG.hidden=SceneThree.hidden=true;SceneSVG.unmount();SceneThree.unmount();const main=$('#main');if(S.page==='factory'){pickScene();main.innerHTML=P.factory();Scene.hidden=false;Scene.mount($('#sceneWrap'));Twin.mount();updateDock();updateFeed()}else{main.innerHTML=(P[S.page]||P.factory)();if(S.page==='review')bindReview();if(S.page==='publish')bindHold()}main.scrollTop=0;renderShell()}
function go(p,tab){S.page=p;S.more=false;if(tab)S.tab=tab;$('#screenSel').value=p;renderPage()}
function refresh(why){renderShell();if(S.page==='factory'){updateDock();updateFeed();Twin.update();if(Scene.host&&Scene.bars){Scene.bars();Scene.relabelBin&&Scene.relabelBin()}}
  else if(why==='gate'&&['inbox','review','publish'].includes(S.page)&&!(document.activeElement&&/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)&&$('#main').contains(document.activeElement))){const y=$('#main').scrollTop;$('#main').innerHTML=P[S.page]();if(S.page==='review')bindReview();if(S.page==='publish')bindHold();$('#main').scrollTop=y}
  else if(why==='events'&&S.page==='activity'){const l=$('#actList');if(l)l.innerHTML=S.events.map(evRow).join('')}}
function updateFeed(){const f=$('#feed');if(f)f.innerHTML=S.events.slice(0,7).map(evRow).join('');const c=$('#stCycle');if(c)c.textContent=SIM.cycle;const d=$('#stDone');if(d)d.textContent=S.done}
function updateDock(){const d=$('#dock');if(!d)return;const q=S.queue[0],p=S.pubq[0];
  if(!q&&!p){d.hidden=true;return}const it=q||p,rev=!!q,more=S.queue.length+S.pubq.length-1;
  d.hidden=false;d.innerHTML=`<div class="t"><span class="thumb" style="background:${posterBg(it.n)}"></span><div style="min-width:0"><b>${esc(it.hook)}</b><span>${rev?t('dock.review'):t('dock.publish')}${more>0?' · +'+more:''}</span></div></div>
  ${rev?`<div class="row"><button class="btn primary sm" data-act="dockapprove">${t('review.approve')}</button><button class="btn sm" data-go="review">${t('dock.open')}</button><button class="btn sm danger" data-act="dockdiscard">${t('review.discard')}</button></div>`
  :`<div class="row" style="flex-wrap:nowrap"><button class="btn primary hold" id="holdBtn" style="flex:1"><i></i><span>${ico('lock','width="15" height="15"')} ${t('pub.hold')}</span></button><button class="btn sm" data-go="publish">${t('dock.open')}</button></div>`}`;bindHold()}
function bindReview(){const ck=[$('#ck1'),$('#ck2'),$('#ck3')],b=$('#btnApprove');if(!b)return;const f=()=>{b.disabled=S.stale||!ck.every(c=>c&&c.checked)};ck.forEach(c=>c&&c.addEventListener('change',f));f()}
function bindHold(){const b=$('#holdBtn');if(!b||b.disabled)return;let tm=null;const start=e=>{if(e.type==='keydown'&&e.key!=='Enter'&&e.key!==' ')return;if(tm)return;b.classList.add('go');tm=setTimeout(()=>{b.classList.remove('go');tm=null;const p=S.pubq[0];if(p)confirmPost(p)},1150)};const stop=()=>{if(tm){clearTimeout(tm);tm=null}b.classList.remove('go')};
  b.addEventListener('pointerdown',start);['pointerup','pointerleave','pointercancel','blur'].forEach(ev=>b.addEventListener(ev,stop));b.addEventListener('keydown',start);b.addEventListener('keyup',stop)}

/* ---------- events (delegation) ---------- */
document.addEventListener('click',e=>{
  const c=e.target.closest('[data-copy]');if(c){copy(c.dataset.copy);return}
  const g=e.target.closest('[data-go]');if(g){e.preventDefault();if(g.dataset.go==='more'){S.more=!S.more;renderShell();return}go(g.dataset.go,g.dataset.tab);return}
  const a=e.target.closest('[data-act]');if(!a)return;const act=a.dataset.act;if(a.tagName==='A')e.preventDefault();
  if(act==='closesheet'){if(e.target===a){S.more=false;renderShell()}}
  else if(act==='pause'){S.loop=S.loop==='running'?'paused':'running';if(S.page==='factory')Twin.update(true);else renderShell()}
  else if(act==='stop'){S.loop=S.loop==='stopped'?'running':'stopped';toast(S.loop==='stopped'?t('toast.stopped'):t('loop.resume'));if(S.page==='factory')Twin.update(true)}
  else if(act==='fail')failItem();
  else if(act==='rail'){S.rail=!S.rail;try{localStorage.setItem(RAILK,S.rail?'1':'0')}catch(e){}renderShell();setTimeout(()=>{if(Scene.host&&Scene.size)Scene.size()},230)}
  else if(act==='resetview'){if(Scene.resetView)Scene.resetView()}
  else if(act==='retry'||act==='skip'){S.fails=S.fails.filter(f=>f.id!==a.dataset.id);refresh('gate');renderPage()}
  else if(act==='login'){const v=($('#otp').value||'').replace(/\D/g,'');if(v.length===6&&v!=='000000'){S.loginErr=false;S.logged=true;go('factory')}else{S.loginErr=true;S.otp=$('#otp').value;renderPage()}}
  else if(act==='dockapprove'){if(S.queue[0])approve(S.queue[0])}
  else if(act==='dockdiscard'){if(S.queue[0])discard(S.queue[0])}
  else if(act==='approve'){const q=S.queue[S.rv];if(q&&!S.stale){approve(q);toast(t('toast.approved'))}}
  else if(act==='changes'){const q=S.queue[S.rv];if(q)discard(q,'changes')}
  else if(act==='discard'){const q=S.queue[S.rv];if(q)discard(q)}
  else if(act==='rv'){S.rv=+a.dataset.i;renderPage()}
  else if(act==='stale'){S.stale=!S.stale;renderPage()}
  else if(act==='theme'){S.theme=a.dataset.id;applyTheme();renderPage();toast(t('toast.theme',{n:TCUR().name[LG()]}))}
  else if(act==='tab'){S.tab=a.dataset.v;renderPage()}
  else if(act==='gen'){toast(t('toast.generated',{n:S.idea.n}))}
  else if(act==='addidea'){S.idea.adding=!S.idea.adding;renderPage()}
  else if(act==='pick'){const i=+a.dataset.i;S.queue.length||0;go('studio')}
  else if(act==='route'){S.route=a.dataset.v;renderPage()}
  else if(act==='render'){S.studio.rendering=true;S.studio.rendered=false;renderPage();setTimeout(()=>{S.studio.rendering=false;S.studio.rendered=true;if(S.page==='studio')renderPage()},1600)}
  else if(act==='read'){toast(t('brand.read.done'))}
  else if(act==='confirmall'){FACTS.forEach(f=>f.v=true);renderPage();toast(t('toast.confirmed'))}
  else if(act==='doctor'){S.doc.running=true;renderPage();setTimeout(()=>{S.doc.running=false;if(S.page==='settings')renderPage()},1200)}
  else if(act==='upd'){S.upd=true;renderPage()}
  else if(act==='clean'){S.clean=true;renderPage()}
  else if(act==='slot'){toast(t('toast.slot'))}
  else if(act==='export'){toast(t('toast.export'))}
  else Twin.act(act,a);
});
document.addEventListener('submit',e=>{if(e.target.id==='chatForm'){e.preventDefault();const i=document.getElementById('chatIn');Chat.send(i.value);i.value=''}});
document.addEventListener('change',e=>{const el=e.target;
  if(el.id==='ul'){S.lang=el.value;applyTheme();renderPage();$('#langSeg').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.l===S.lang))}
  else if(el.id==='rtlSw'){S.rtl=el.checked;applyTheme()}
  else if(el.id==='redSw'){S.reduce=el.checked;applyTheme()}
  else if(el.id==='nn'){S.idea.n=+el.value}
  else if(el.id==='sd'){$('#sdv').textContent=el.value}});
document.addEventListener('input',e=>{if(e.target.id==='sd')$('#sdv').textContent=e.target.value});
document.addEventListener('keydown',e=>{if(S.page!=='review'||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;const q=S.queue[S.rv];if(!q)return;
  if(e.key==='a'||e.key==='A'){const b=$('#btnApprove');if(b&&!b.disabled)approve(q)}else if(e.key==='d'||e.key==='D')discard(q);else if(e.key==='n'||e.key==='N')discard(q,'changes');
  else if(e.key==='ArrowRight'){S.rv=Math.min(S.queue.length-1,S.rv+1);renderPage()}else if(e.key==='ArrowLeft'){S.rv=Math.max(0,S.rv-1);renderPage()}});

/* ---------- prototype controls ---------- */
function buildControls(){
  $('#screenSel').innerHTML=['login'].concat(PAGES).map(k=>`<option value="${k}">${t(k==='login'?'nav.login':'nav.'+k)}</option>`).join('');$('#screenSel').value=S.page;
  $('#viewSel').innerHTML=[['3d',t('view.3d')],['3d-sprites',t('view.sprites')],['2d',t('view.2d')]].map(([v,l])=>`<option value="${v}">${l}</option>`).join('');$('#viewSel').value=S.view;
  $('#themeSel').innerHTML=THEME_ORDER.map(id=>`<option value="${id}">${TH[id].name[LG()]}${TH[id].status==='mvp'?' · MVP':' · concept'}</option>`).join('');$('#themeSel').value=S.theme;
  $$('#devSeg button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.d===S.device));$$('#langSeg button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.l===S.lang));
  $('#autoChk').checked=S.auto;$('#rtlChk').checked=S.rtl;$('#upChk').checked=S.canUpload;$('#pTitle').textContent=t('proto.title');$('#pSub').textContent=t('proto.sub');
  [['lblScreen','proto.screen'],['lblTheme','proto.theme'],['lblView','proto.view'],['lblAuto','proto.auto'],['lblRtl','proto.rtl'],['lblUp','proto.up']].forEach(([i,k])=>{const n=$('#'+i);if(n)n.textContent=t(k)});
  [['n1','proto.n1'],['n2','proto.n2'],['n3','proto.n3']].forEach(([i,k])=>{$('#'+i).innerHTML=t(k)})}
function wireControls(){
  $('#screenSel').addEventListener('change',e=>go(e.target.value));
  $('#themeSel').addEventListener('change',e=>{S.theme=e.target.value;applyTheme();renderPage()});
  $('#viewSel').addEventListener('change',e=>{S.view=e.target.value;renderPage()});
  $('#devSeg').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;S.device=b.dataset.d;buildControls();applyTheme();renderPage()});
  $('#langSeg').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;S.lang=b.dataset.l;buildControls();applyTheme();renderPage()});
  $('#autoChk').addEventListener('change',e=>{S.auto=e.target.checked});
  $('#rtlChk').addEventListener('change',e=>{S.rtl=e.target.checked;applyTheme()});
  $('#upChk').addEventListener('change',e=>{S.canUpload=e.target.checked;if(S.page==='publish')renderPage()});
  const mq=matchMedia('(max-width: 520px)');const f=()=>{if(mq.matches){S.device='phone';$('#devSeg').hidden=true}else $('#devSeg').hidden=false;applyTheme()};mq.addEventListener&&mq.addEventListener('change',()=>{f();renderPage()});f()}


/* ---------- boot ---------- */
function seed(){
  const mk=(i,hook)=>({id:'itm_'+String(100+i),hook,fam:FAM[i%5],n:i+2,since:-99,dur:15,hash:hex('seed'+i)});
  S.queue.push(mk(1,HOOKS[S.lang][1]),mk(2,HOOKS[S.lang][2]));
  const base=Date.now();[['brand.checked',{facts:6},-420],['ideas.generated',{n:5},-380],['make.rendered',{s:15},-300],['gate.review',{},-240],['metrics.ingested',{d:3,views:'3,2k',delta:'+21%'},-120],['report.generated',{family:t('fam.tip'),n:8},-90]]
   .forEach(([k,d,o])=>{S.events.push({id:++EVN,ts:new Date(base+o*1000),kind:k,data:d,stage:STAGE_OF[k]||null})});S.events.reverse();
  S.pubq.push({id:'itm_099',hook:HOOKS[S.lang][2],fam:'offer',n:4,since:-99,hash:hex('pub99')});
  if(S.page==='inbox'&&Q.get('fail')==='1')S.fails.push({id:'itm_098',hook:HOOKS[S.lang][0]})}
let last=performance.now();
function frame(now){window.__fr=(window.__fr||0)+1;const dt=Math.min(.06,(now-last)/1000);last=now;if(!document.hidden){stepSim(dt);if(Scene.host)Scene.draw(dt);if(Twin.root)Twin.tick(dt)}requestAnimationFrame(frame)}
window.addEventListener('DOMContentLoaded',()=>{
  if(Q.get('scheme'))document.documentElement.dataset.theme=Q.get('scheme');
  S.tod=todDefault();geoInit();seed();Chat.seed();buildControls();wireControls();applyTheme();renderPage();
  if(Q.get('warm')){const n=+Q.get('warm');for(let i=0;i<n*30;i++)stepSim(1/30)}
  requestAnimationFrame(frame)});
