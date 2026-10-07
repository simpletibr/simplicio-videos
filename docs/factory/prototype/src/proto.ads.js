/* ===== Ad market (prototype). Every house, balloon and billboard in the world is a slot anyone can rent for a few hours,
   for the whole world, one country or one region. The price moves with supply and demand, like an ad auction.
   Static reviewed images only, always marked "Ad", never ad scripts, never inside generated videos.
   All numbers here are made up: no real money moves, bookings live only in this tab. Spec: docs/factory/ads.md ===== */
Object.assign(ICON,{ads:'<rect x="3" y="4" width="18" height="10" rx="2"/><path d="M8 14v6M16 14v6M7 8h6M7 11h10"/>',tag:'<path d="M3 12l9-9h8v8l-9 9z"/><circle cx="16" cy="8" r="1.5"/>'});

/* geography: world -> country -> region. share = share of all sessions, tier = how much advertisers pay there (relative) */
const AD_GEO=[
 {id:'BR',n:['Brazil','Brasil'],share:.34,tier:.7,tz:-3,r:[['SP','São Paulo',.32],['RJ','Rio de Janeiro',.12],['MG','Minas Gerais',.1],['BA','Bahia',.07],['RS','Rio Grande do Sul',.06],['PR','Paraná',.06],['PE','Pernambuco',.04],['CE','Ceará',.04],['XX',null,.19]]},
 {id:'US',n:['United States','Estados Unidos'],share:.22,tier:1.8,tz:-5,r:[['CA','California',.2],['TX','Texas',.1],['NY','New York',.1],['FL','Florida',.08],['XX',null,.52]]},
 {id:'MX',n:['Mexico','México'],share:.1,tier:.55,tz:-6,r:[['CDMX','Ciudad de México',.25],['JAL','Jalisco',.1],['NLE','Nuevo León',.1],['XX',null,.55]]},
 {id:'DE',n:['Germany','Alemanha'],share:.08,tier:1.5,tz:1,r:[['BY','Bayern',.2],['BE','Berlin',.1],['NW','Nordrhein-Westfalen',.2],['XX',null,.5]]},
 {id:'JP',n:['Japan','Japão'],share:.06,tier:1.4,tz:9,r:[['TK','Tokyo',.3],['OS','Osaka',.15],['XX',null,.55]]},
 {id:'PT',n:['Portugal','Portugal'],share:.05,tier:.9,tz:0,r:[['LI','Lisboa',.4],['PO','Porto',.25],['XX',null,.35]]},
 {id:'ZZ',n:['Rest of the world','Resto do mundo'],share:.15,tier:1,tz:0,r:[['XX',null,1]]}];

/* what can be rented: three spaces per house, two for the whole world */
const AD_KIND={board:{r:.55,en:'Billboard',pt:'Outdoor',ico:'ads'},banner:{r:.35,en:'Belt flags',pt:'Bandeiras da esteira',ico:'tag'},balloon:{r:.45,en:'Balloon',pt:'Balão',ico:'cloud'},blimp:{r:.6,en:'Blimp',pt:'Dirigível',ico:'cloud'},floor:{r:.5,en:'Plaza floor',pt:'Piso da praça',ico:'tag'}};
const AD_VISIT={brand:.22,ideas:.25,make:.45,review:.5,publish:.5,metrics:.2,report:.15,world:.3};   // share of sessions that see that house (or the world view)
const AD_SLOTS=[];STAGES.forEach(k=>['board','banner','balloon'].forEach(kd=>AD_SLOTS.push({id:k+'.'+kd,stage:k,kind:kd})));AD_SLOTS.push({id:'world.blimp',stage:null,kind:'blimp'},{id:'world.floor',stage:null,kind:'floor'});
const AD_PAL=[['#7a4a2b','#e9a35c'],['#1f6f4a','#7fd6a1'],['#2a62c9','#8fc3ff'],['#c2548a','#ffb3d1'],['#6b3fd1','#c3a6ff'],['#d14b2f','#ffc27a']];
const FX_BRL=5.4;

const ADS={ver:0,viewer:null,sel:null,bookings:[],mine:0,
  /* ---------- geography helpers ---------- */
  nodes:null,
  build(){if(this.nodes)return;const m={world:{id:'world',level:0,share:1,tier:1,tz:0,kids:[]}};m.world.parent=null;
    AD_GEO.forEach(c=>{const cn={id:c.id,level:1,share:c.share,tier:c.tier,tz:c.tz,parent:m.world,geo:c,kids:[]};m[c.id]=cn;m.world.kids.push(cn);
      c.r.forEach(([rid,nm,sh])=>{const rn={id:c.id+'/'+rid,level:2,share:c.share*sh,tier:c.tier,tz:c.tz,parent:cn,geo:c,rid,rname:nm,kids:[]};m[rn.id]=rn;cn.kids.push(rn)})});this.nodes=m},
  node(id){this.build();return this.nodes[id]},
  leaves(n){return n.level===2?[n]:n.kids.flatMap(k=>this.leaves(k))},
  covers(a,b){for(let x=b;x;x=x.parent)if(x===a)return true;return false},   // is b inside a (or equal)
  related(a,b){return this.covers(a,b)||this.covers(b,a)},
  label(n){if(n.level===0)return t('ads.world');if(n.level===1)return n.geo.n[lk()];return (n.rname||t('ads.rest'))+' · '+n.geo.id},
  defViewer(){return S.lang==='pt-BR'?'BR/SP':'US/CA'},
  vnode(){this.build();return this.node(this.viewer||this.defViewer())},
  /* ---------- the clock ---------- */
  hNow(){return Math.floor(Date.now()/36e5)},
  hh(h){const d=new Date(h*36e5);return String(d.getHours()).padStart(2,'0')+':00'},
  /* ---------- hash noise, so the same hour gives the same market ---------- */
  hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return ((h>>>0)%10007)/10007},
  curve(n,h){const lh=((h+n.tz)%24+24)%24;return .25+.75*Math.max(0,Math.sin(Math.PI*(lh-6)/17))},
  /* ---------- the price: floor (audience) x demand multiplier x lead time ---------- */
  sessions(n,h){return 20000*n.share*this.curve(n,h)},
  slot(id){return AD_SLOTS.find(s=>s.id===id)},
  leafPrice(sl,n,h,info){const kd=AD_KIND[sl.kind],vis=AD_VISIT[sl.stage||'world'],imp=this.sessions(n,h)*kd.r*vis*12;   // 12 views per session
    const floor=Math.max(.4,imp/1000*2*n.tier);
    const rho=this.util(n,h),dem=this.demand(sl,n,h),m=1+2.2*Math.pow(rho,1.5)+1.6*dem*dem,tts=h-this.hNow(),lt=tts<=0?1:tts<3?.75+.08*tts:tts>48?.88:1;
    const price=Math.max(.5,floor*m*lt);if(info){info.imp=imp;info.floor=floor;info.rho=rho;info.dem=dem;info.mult=m;info.lt=lt}return price},
  util(n,h){let taken=0;for(const b of this.bookings){if(h<b.start||h>=b.start+b.hours)continue;if(this.related(b.node,n))taken++}return Math.min(1,taken/AD_SLOTS.length*2.2)},   // share of the 23 spaces already rented there at that hour
  demand(sl,n,h){const day=this.hash(sl.id+'|'+n.id+'|'+h),drift=.5+.5*Math.sin(Date.now()/9e4+this.hash(sl.id)*6.28),peak=this.curve(n,h);return Math.max(.04,Math.min(1,.25*day+.4*peak+.35*drift*day))},   // other advertisers watching or bidding
  /* a bundle (country or world) is the sum of its free regions, with a volume discount */
  quoteHour(sl,n,h){const ls=this.leaves(n),free=ls.filter(l=>this.free(sl,l,h)),disc=n.level===0?.88:n.level===1?.92:1;let sum=0;free.forEach(l=>{sum+=this.leafPrice(sl,l,h)});
    const info={};if(n.level===2)this.leafPrice(sl,n,h,info);else{const l0=ls[0];this.leafPrice(sl,l0,h,info)}
    return{price:sum*(free.length===ls.length?disc:1),free:free.length,all:ls.length,info}},
  free(sl,n,h){return !this.bookings.some(b=>b.slot===sl.id&&h>=b.start&&h<b.start+b.hours&&this.related(b.node,n))},
  quote(slotId,nodeId,off,hours){const sl=this.slot(slotId),n=this.node(nodeId),h0=this.hNow()+off,rows=[];let total=0,partial=false,blocked=null;
    for(let i=0;i<hours;i++){const q=this.quoteHour(sl,n,h0+i);if(!q.free){blocked=blocked||this.bookings.find(b=>b.slot===slotId&&this.related(b.node,n)&&h0+i>=b.start&&h0+i<b.start+b.hours)}if(q.free<q.all)partial=true;rows.push({h:h0+i,price:q.price,free:q.free,all:q.all,info:q.info});total+=q.price}
    return{rows,total,partial,blocked,none:rows.every(r=>!r.free),n}},
  /* ---------- buying: posted price now, or a bid in a second-price auction against other advertisers ---------- */
  book(slotId,nodeId,off,hours,cr,mode,bidK){const q=this.quote(slotId,nodeId,off,hours);if(q.partial||q.none)return{ok:false,why:'taken'};let pay=q.total;
    if(mode==='bid'){pay=0;for(const r of q.rows){const rival=r.price*(.7+.75*this.hash('bid|'+slotId+'|'+nodeId+'|'+r.h)),mine=r.price*bidK,floor=r.info.floor;if(mine<rival)return{ok:false,why:'outbid',rival:rival,mine:mine,h:r.h};pay+=Math.max(floor,rival+.01)}}
    const b={id:'ad_'+(++this.mine),slot:slotId,node:q.n,start:this.hNow()+off,hours,brand:cr.brand,line:cr.line,pal:cr.pal,price:pay,mine:true};this.bookings.push(b);this.ver++;return{ok:true,b,saved:q.total-pay}},
  cancel(id){const i=this.bookings.findIndex(b=>b.id===id&&b.mine);if(i>=0){this.bookings.splice(i,1);this.ver++}},
  /* what the viewer sees on a slot right now: the most specific rental that covers them */
  adFor(slotId){const h=this.hNow(),v=this.vnode();const c=this.bookings.filter(b=>b.slot===slotId&&h>=b.start&&h<b.start+b.hours&&this.covers(b.node,v)).sort((a,b)=>b.node.level-a.node.level);return c[0]||null},
  seed(){this.build();const h=this.hNow(),B=(slot,node,start,hours,brand,line,pal)=>this.bookings.push({id:'ad_s'+this.bookings.length,slot,node:this.node(node),start:h+start,hours,brand,line,pal:AD_PAL[pal],price:0,mine:false});
    B('make.board','BR',-1,6,'Café Aurora','Roasted at sunrise',0);B('review.balloon','world',0,3,'Vento Sneakers','Run lighter',2);B('publish.board','BR/SP',-2,5,'Padaria Lume','Warm bread, 6 am',5);B('world.blimp','US',0,4,'Norte Bank','Save with a smile',2);
    B('brand.banner','PT',-1,8,'Sol Seguros','Peace of mind',4);B('metrics.board','world',1,4,'Lumen Phone','See it all',4);B('report.balloon','MX',0,5,'Taco Sol','Hot, fast, fresh',5);B('ideas.board','BR/RJ',-3,6,'Samba Tour','Rio, your way',3);
    B('make.banner','world',-1,2,'Brisa Water','Stay fresh',2);B('publish.balloon','BR',0,6,'Cacau Doce','Sweet little things',3);B('world.floor','world',-1,3,'Nuvem Cloud','Your files, floating',4);B('review.board','DE',0,5,'Wald Bikes','Ride the forest',1)},
  money(usd){if(S.lang==='pt-BR'){const v=usd*FX_BRL;return 'R$ '+(v<10?v.toFixed(2):Math.round(v)).toString().replace('.',',')}return '$'+(usd<10?usd.toFixed(2):Math.round(usd))},
  /* ---------- painting the creatives (canvas) ---------- */
  paint(g,w,h,slotId,compact){const b=this.adFor(slotId),sl=this.slot(slotId),narrow=h>w*1.4;g.save();
    if(b){const gr=g.createLinearGradient(0,0,w,h);gr.addColorStop(0,b.pal[0]);gr.addColorStop(1,b.pal[1]);g.fillStyle=gr;g.fillRect(0,0,w,h);
      g.fillStyle='rgba(255,255,255,.14)';g.beginPath();g.arc(w*.82,h*.2,Math.min(w,h)*.5,0,7);g.fill();g.beginPath();g.arc(w*.1,h*.95,Math.min(w,h)*.38,0,7);g.fill();
      g.fillStyle='#fff';g.textAlign='center';g.textBaseline='middle';g.shadowColor='rgba(0,0,0,.35)';g.shadowBlur=w*.01;
      const fs=narrow?w*.2:Math.min(h*.2,w*.1);g.font=`800 ${fs}px "Bricolage Grotesque","Avenir Next",system-ui,sans-serif`;
      if(narrow){const parts=String(b.brand).split(' ');parts.forEach((p,i)=>g.fillText(p,w/2,h*.34+i*fs*1.05))}else g.fillText(b.brand,w/2,h*.42,w*.9);
      g.shadowBlur=0;g.font=`600 ${narrow?w*.13:Math.min(h*.1,w*.05)}px "Instrument Sans",system-ui,sans-serif`;g.fillStyle='rgba(255,255,255,.95)';if(narrow){const ws=String(b.line).split(' ');ws.slice(0,4).forEach((p,i)=>g.fillText(p,w/2,h*.62+i*w*.15))}else g.fillText(b.line,w/2,h*.64,w*.9)}
    else{g.fillStyle='#fff7d6';g.fillRect(0,0,w,h);g.strokeStyle='#f0b43c';g.lineWidth=Math.max(6,w*.012);g.setLineDash([w*.04,w*.025]);g.strokeRect(g.lineWidth,g.lineWidth,w-g.lineWidth*2,h-g.lineWidth*2);g.setLineDash([]);
      g.fillStyle='#8a5a00';g.textAlign='center';g.textBaseline='middle';const q=this.quoteHour(sl,this.vnode(),this.hNow()),fs=narrow?w*.17:Math.min(h*.17,w*.085);
      g.font=`800 ${fs}px "Bricolage Grotesque","Avenir Next",system-ui,sans-serif`;if(narrow){['YOUR','AD','HERE'].forEach((p,i)=>g.fillText(p,w/2,h*.28+i*fs*1.1))}else g.fillText(t('ads.here'),w/2,h*.4,w*.92);
      g.font=`700 ${narrow?w*.15:Math.min(h*.11,w*.055)}px "Instrument Sans",system-ui,sans-serif`;g.fillStyle='#b27300';g.fillText(t('ads.from',{p:this.money(q.price)}),w/2,narrow?h*.74:h*.66,w*.9)}
    // always marked as an ad
    const tg=Math.max(14,Math.min(w,h)*.085);g.font=`700 ${tg}px "Instrument Sans",system-ui,sans-serif`;g.textAlign='left';g.textBaseline='top';const lab=b?t('ads.tag'):t('ads.space');const tw=g.measureText(lab).width+tg*.9;
    g.fillStyle='rgba(15,34,51,.78)';g.fillRect(0,0,tw,tg*1.5);g.fillStyle='#fff';g.fillText(lab,tg*.45,tg*.22);g.restore()},
  thumb(slotId,w,h){const b=this.adFor(slotId),key=[slotId,w,h,S.lang,b?b.id:Math.round(this.quoteHour(this.slot(slotId),this.vnode(),this.hNow()).price*2)].join('|');this._th=this._th||new Map();if(this._th.has(key))return this._th.get(key);if(this._th.size>400)this._th.clear();const c=document.createElement('canvas');c.width=w;c.height=h;this.paint(c.getContext('2d'),w,h,slotId);const u=c.toDataURL('image/webp',.8);this._th.set(key,u);return u},
  /* ---------- the page ---------- */
  st(){return S.ads||(S.ads={reach:'country',country:S.lang==='pt-BR'?'BR':'US',region:'XX',off:1,hours:4,mode:'now',bid:1,brand:'',line:'',pal:0,sort:'price'})},
  target(){const a=this.st();return a.reach==='world'?'world':a.reach==='country'?a.country:a.country+'/'+a.region},
  slotName(s){return s.stage?t('station.'+s.stage)+' · '+AD_KIND[s.kind][LG()]:(s.kind==='blimp'?t('ads.world')+' · ':t('ads.world')+' · ')+AD_KIND[s.kind][LG()]},
  cards(){const a=this.st(),tn=this.target(),hr=this.hNow(),rows=AD_SLOTS.map(sl=>{const q=this.quote(sl.id,tn,a.off,a.hours),cur=this.adFor(sl.id),info=q.rows[0].info;return{sl,q,cur,info}});
    rows.sort((x,y)=>a.sort==='demand'?y.info.dem-x.info.dem:a.sort==='name'?this.slotName(x.sl).localeCompare(this.slotName(y.sl)):y.q.total-x.q.total);
    return rows.map(({sl,q,cur,info})=>{const sel=this.sel===sl.id,none=q.none||(q.partial&&a.reach!=='region'&&q.rows.every(r=>r.free===0)),blocked=q.none;
      const status=q.partial&&!q.none?t('ads.partial',{n:q.rows[0].free,m:q.rows[0].all}):blocked?t('ads.taken',{who:q.blocked?q.blocked.brand:'',t:q.blocked?this.hh(q.blocked.start+q.blocked.hours):''}):'';
      return `<article class="adcard ${sel?'sel':''} ${blocked?'off':''}" data-slot="${sl.id}"><img class="adth" alt="" src="${this.thumb(sl.id,sl.kind==='banner'?120:320,sl.kind==='banner'?280:180)}"><div class="adb">
        <b>${esc(this.slotName(sl))}</b><small>${cur?t('ads.now',{b:esc(cur.brand),w:esc(this.label(cur.node))}):t('ads.vacant')}</small>
        <div class="adm"><span title="${t('ads.m.imp')}">${ico('eye','width="13" height="13"')}${Math.round(info.imp/1000*10)/10}k</span><span class="chip ${info.mult>2.4?'hot':info.mult>1.6?'warm':''}" title="${t('ads.m.mult')}">×${info.mult.toFixed(1)}</span><span title="${t('ads.m.util')}">${Math.round(info.rho*100)}%</span></div>
        <div class="adp"><b>${this.money(q.total)}</b><small>${t('ads.for',{h:a.hours,p:this.money(q.total/a.hours)})}</small></div>
        ${status?`<small class="adst">${status}</small>`:''}
        <button class="btn sm ${blocked?'':'primary'}" data-act="adbuy" data-slot="${sl.id}" ${blocked?'disabled':''}>${a.mode==='bid'?t('ads.bid'):t('ads.buy')}</button></div></article>`}).join('')},
  mineHTML(){const hn=this.hNow(),mine=this.bookings.filter(b=>b.mine);if(!mine.length)return `<p class="qe">${t('ads.none')}</p>`;
    return mine.map(b=>`<div class="adrow"><img class="adth" alt="" src="${this.thumb(b.slot,96,54)}"><div><b>${esc(b.brand)}</b><small>${esc(this.slotName(this.slot(b.slot)))} · ${esc(this.label(b.node))}</small><small>${this.hh(b.start)}–${this.hh(b.start+b.hours)} · ${hn>=b.start&&hn<b.start+b.hours?t('ads.live'):hn<b.start?t('ads.soon'):t('ads.done')}</small></div><b>${this.money(b.price)}</b><button class="tbtn sm" data-act="adcancel" data-id="${b.id}" aria-label="${t('ads.cancel')}" title="${t('ads.cancel')}">${ico('close')}</button></div>`).join('')},
  explain(){const a=this.st(),id=this.sel||'make.board',sl=this.slot(id),n=this.node(this.target()),h=this.hNow()+a.off,l=this.leaves(n)[0],info={};this.leafPrice(sl,l,h,info);
    return `<div class="adx"><b>${esc(this.slotName(sl))} · ${esc(this.label(l))}</b>
      <ol><li>${t('ads.x1',{i:Math.round(info.imp),f:this.money(info.floor)})}</li><li>${t('ads.x2',{u:Math.round(info.rho*100),d:Math.round(info.dem*100),m:info.mult.toFixed(2)})}</li><li>${t('ads.x3',{k:info.lt.toFixed(2)})}</li><li>${t('ads.x4')}</li></ol>
      <p class="ads-formula mono">${t('ads.formula')}</p></div>`},
  page(){this.build();if(!this.bookings.length)this.seed();const a=this.st(),vn=this.vnode(),L=LG(),cn=this.node(a.country);
    const opt=(v,l,sel)=>`<option value="${v}" ${sel?'selected':''}>${esc(l)}</option>`,seg=(k,list)=>`<div class="seg" role="group">${list.map(([v,l])=>`<button type="button" data-act="adset" data-k="${k}" data-v="${v}" aria-pressed="${String(a[k])===String(v)}">${l}</button>`).join('')}</div>`;
    const cr=this.creative(),pal=AD_PAL.map((p,i)=>`<button type="button" class="sw" data-act="adset" data-k="pal" data-v="${i}" aria-pressed="${a.pal===i}" style="background:linear-gradient(135deg,${p[0]},${p[1]})" aria-label="${i+1}"></button>`).join('');
    return `<div class="head"><div><h1>${t('ads.h')}</h1><p class="lead">${t('ads.lead')}</p></div></div>
    <div class="card adnote">${ico('eye','width="16" height="16"')}<span>${t('ads.rules')}</span></div>
    <div class="card adctl"><div class="adf"><label>${t('ads.reach')}</label>${seg('reach',[['world',t('ads.world')],['country',t('ads.country')],['region',t('ads.region')]])}</div>
      <div class="adf" ${a.reach==='world'?'hidden':''}><label>${t('ads.where')}</label><select data-act="adsel" data-k="country" aria-label="${t('ads.country')}">${AD_GEO.map(c=>opt(c.id,c.n[lk()],a.country===c.id)).join('')}</select>
        <select data-act="adsel" data-k="region" aria-label="${t('ads.region')}" ${a.reach!=='region'?'hidden':''}>${cn.kids.map(r=>opt(r.rid,r.rname||t('ads.rest'),a.region===r.rid)).join('')}</select></div>
      <div class="adf"><label>${t('ads.start')}</label><select data-act="adsel" data-k="off">${Array.from({length:13},(_,i)=>opt(i,i===0?t('ads.nowh'):'+'+i+' h · '+this.hh(this.hNow()+i),a.off===i)).join('')}</select></div>
      <div class="adf"><label>${t('ads.hours')}</label>${seg('hours',[[1,'1 h'],[2,'2 h'],[4,'4 h'],[8,'8 h']])}</div>
      <div class="adf"><label>${t('ads.mode')}</label>${seg('mode',[['now',t('ads.m.now')],['bid',t('ads.m.bid')]])}<select data-act="adsel" data-k="bid" ${a.mode!=='bid'?'hidden':''} aria-label="${t('ads.maxbid')}">${[.7,.85,1,1.25].map(v=>opt(v,t('ads.maxbidv',{p:Math.round(v*100)}),a.bid==v)).join('')}</select></div>
      <div class="adf wide"><label>${t('ads.creative')}</label><input type="text" maxlength="18" data-act="adin" data-k="brand" placeholder="${t('ads.brand.ph')}" value="${esc(a.brand)}"><input type="text" maxlength="28" data-act="adin" data-k="line" placeholder="${t('ads.line.ph')}" value="${esc(a.line)}"><div class="sws">${pal}</div></div>
      <div class="adf wide adview"><label>${t('ads.viewer')}</label><select data-act="adsel" data-k="vcountry">${AD_GEO.map(c=>opt(c.id,c.n[lk()],vn.geo.id===c.id)).join('')}</select><select data-act="adsel" data-k="vregion">${vn.parent.kids.map(r=>opt(r.rid,r.rname||t('ads.rest'),vn.rid===r.rid)).join('')}</select><small>${t('ads.viewer.n')}</small></div></div>
    <div class="adwrap"><div class="adhead"><b>${t('ads.slots')}</b><div class="seg">${[['price',t('ads.sort.price')],['demand',t('ads.sort.demand')],['name',t('ads.sort.name')]].map(([v,l])=>`<button type="button" data-act="adset" data-k="sort" data-v="${v}" aria-pressed="${a.sort===v}">${l}</button>`).join('')}</div></div><div class="adgrid" id="adGrid">${this.cards()}</div></div>
    <div class="adtwo"><div class="card"><h4>${t('ads.how')}</h4><div id="adExplain">${this.explain()}</div></div><div class="card"><h4>${t('ads.mine')}</h4><div id="adMine">${this.mineHTML()}</div></div></div>`},
  creative(){const a=this.st();return{brand:(a.brand||'').trim()||t('ads.brand.def'),line:(a.line||'').trim()||t('ads.line.def'),pal:AD_PAL[a.pal]}},
  /* updates only what changes with the market so inputs keep focus */
  live(){if(S.page!=='ads')return;const g=document.getElementById('adGrid');if(!g)return;const y=document.getElementById('main').scrollTop;g.innerHTML=this.cards();const e=document.getElementById('adExplain'),m=document.getElementById('adMine');if(e)e.innerHTML=this.explain();if(m)m.innerHTML=this.mineHTML()},
  act(a,el){const st=this.st();
    if(a==='adset'){let v=el.dataset.v;st[el.dataset.k]=/^\d+$/.test(v)?+v:v;if(el.dataset.k==='reach'&&v==='region')st.region=this.node(st.country).kids[0].rid;this.ver++;renderPage();return true}
    if(a==='adsel'){const k=el.dataset.k;if(k==='vcountry'){const c=this.node(el.value);this.viewer=el.value+'/'+c.kids[0].rid}else if(k==='vregion'){this.viewer=this.vnode().geo.id+'/'+el.value}else{st[k]=k==='bid'?+el.value:(k==='off'?+el.value:el.value);if(k==='country')st.region=this.node(el.value).kids[0].rid}this.ver++;renderPage();return true}
    if(a==='adin'){return true}
    if(a==='adbuy'){const sl=this.slot(el.dataset.slot);this.sel=sl.id;const cr=this.creative(),r=this.book(sl.id,this.target(),st.off,st.hours,cr,st.mode,st.bid);
      if(r.ok){toast(t('ads.ok',{n:this.slotName(sl)}))}else if(r.why==='outbid'){toast(t('ads.outbid',{r:this.money(r.rival),m:this.money(r.mine)}))}else toast(t('ads.nope'));renderPage();return true}
    if(a==='adcancel'){this.cancel(el.dataset.id);renderPage();return true}
    if(a==='adcard'){this.sel=el.dataset.slot;this.live();return true}
    return false}
};

/* ---------- the spaces themselves, in the 3D world ---------- */
Object.assign(SceneThree,{
  adTex(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=4;return{c,t,w,h}},
  buildAds(world){ADS.build();if(!ADS.bookings.length)ADS.seed();this.adSlots={};this.adSig='';const A=this.anims,ink=this.th.p.ink;
    const reg=(id,w,h,grp)=>{const tx=this.adTex(w,h);this.adSlots[id]={tx,id,env:null};grp.userData.adSlot=id;this.adObjs.push(grp);return tx},
      face=(tx,pw,ph)=>{const m=new THREE.Mesh(new THREE.PlaneGeometry(pw,ph),new THREE.MeshBasicMaterial({map:tx.t,side:THREE.DoubleSide}));return m};
    STAGES.forEach((k,i)=>{const P=this.pl[k],g=P.g,W=P.W,side=i%2?1:-1,sc=new THREE.Group();g.add(sc);
      // billboard high on two posts behind the house
      {const b=new THREE.Group(),tx=reg(k+'.board',640,360,b);b.add(bx(10.6,6.2,.5,'#2a3340',0,0,-.05),face(tx,10,5.6),cy(.22,.28,9,'#4a4f57',-3.6,-7.6,-.3,8),cy(.22,.28,9,'#4a4f57',3.6,-7.6,-.3,8));b.children[1].position.z=.22;b.position.set(W/2+3,8.8,-12);b.scale.setScalar(.88);sc.add(b);b.traverse(o=>{if(o.isMesh&&o.material.isMeshLambertMaterial){o.castShadow=true}});this.bob(b,.12,.6,i)}
      // flags on two poles at the belt
      {const f=new THREE.Group(),tx=reg(k+'.banner',140,320,f);[-1,1].forEach(s=>{const pole=new THREE.Group();pole.add(cy(.08,.1,6.2,'#4a4f57',0,3.1,0,6));const fl=face(tx,1.9,4.3);fl.position.set(1.05,3.9,0);pole.add(fl,sp(.2,'#ffd23f',0,6.3,0,6));pole.position.set(s*(W/2+3.4),0,5.4);f.add(pole);this.sway(pole,.035,1.3,s+i)});sc.add(f)}
      // a balloon drifting in the sky, the ad hangs under it
      {const bl=new THREE.Group(),tx=reg(k+'.balloon',512,288,bl),env=new THREE.Mesh(new THREE.SphereGeometry(2.7,14,12),LM('#f0b43c'));env.scale.y=1.18;this.adSlots[k+'.balloon'].env=env;
        const pn=face(tx,7.2,4.05);pn.position.set(0,-6.2,0);bl.add(env,pn,bx(1,.8,1,'#a9703f',0,-3.9,0),cy(.04,.04,3.2,'#555',-.45,-4.8,0,4),cy(.04,.04,3.2,'#555',.45,-4.8,0,4));bl.position.set(-W*.2,13.5,-16);bl.scale.setScalar(.82);sc.add(bl);this.bob(bl,.7,.45,i*1.3);A.push(t=>{if(!S.reduce)bl.rotation.y=Math.sin(t*.25+i)*.25})}});
    // the whole-world spaces: a blimp circling the ring and a big decal on the plaza (seen from above)
    this.adWorld=new THREE.Group();world.add(this.adWorld);
    {const b=new THREE.Group(),tx=reg('world.blimp',768,240,b),body=new THREE.Mesh(new THREE.SphereGeometry(1,16,12),LM('#f2f4f7'));body.scale.set(9,2.9,2.9);b.add(body,bx(1.4,3.2,.2,'#e5483b',-8.5,1.2,0),bx(1.4,.2,3.2,'#e5483b',-8.5,0,0),bx(2.2,1,1.6,'#6b7787',0,-3.1,0));
      const p1=face(tx,13,4.05);p1.position.set(0,0,2.95);const p2=face(tx,13,4.05);p2.position.set(0,0,-2.95);p2.rotation.y=Math.PI;const p3=face(tx,13,4.05);p3.rotation.x=-Math.PI/2;p3.position.set(0,2.95,0);b.add(p1,p2,p3);b.position.y=34;this.adWorld.add(b);this.blimp=b;A.push(t=>{const a=t*.05;b.position.set(Math.cos(a)*36,34+Math.sin(t*.4)*.8,Math.sin(a)*36);b.rotation.y=-a+Math.PI})}
    {const f=new THREE.Group(),tx=reg('world.floor',768,432,f),pl=face(tx,24,13.5);pl.rotation.x=-Math.PI/2;pl.position.y=.09;f.add(pl);f.position.set(8,0,-10);this.adWorld.add(f)}
    this.adWorld.visible=false},
  adRepaint(){const sig=ADS.ver+'|'+ADS.hNow()+'|'+ADS.viewer+'|'+S.lang+'|'+Math.floor(Date.now()/8000);if(sig===this.adSig)return;this.adSig=sig;
    for(const id in this.adSlots){const sl=this.adSlots[id],g=sl.tx.c.getContext('2d');ADS.paint(g,sl.tx.w,sl.tx.h,id);sl.tx.t.needsUpdate=true;if(sl.env){const b=ADS.adFor(id);sl.env.material.color.set(b?b.pal[0]:'#f0b43c')}}}
});
