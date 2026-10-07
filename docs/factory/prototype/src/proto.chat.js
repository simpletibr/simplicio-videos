/* ===== Bots: a chat with the eight agents, in the style of companion-chat apps (avatar row, bubbles, quick
   replies, one input). Replies are catalog templates picked by simple intents, so the prototype spends zero
   tokens; in the product the same panel can talk to real agents. The bots also control the world: weather,
   day and night, camera follow and fly-over. ===== */
Object.assign(ICON,{cloud:'<path d="M7 18a4 4 0 010-8 5 5 0 019.6-1A4.5 4.5 0 0117 18z"/>',chat:'<path d="M4 5.5h16v10.5H10l-4.5 3.5V16H4z"/>'});
const BOT_ROLES=['brander','ideator','director','gatekeeper','poster','analyst','reflector','evolver'];
const ROLE_STAGE={brander:'brand',ideator:'ideas',director:'make',gatekeeper:'review',poster:'publish',analyst:'metrics',reflector:'report',evolver:'report'};
const INTENTS=[['stop',/parar de seguir|stop follow|pare de|solta/i],['follow',/segu|follow|acompanh|me leva|take me|ande comigo|walk with/i],
  ['wx','rain',/chuv|rain|storm|tempest/i],['wx','snow',/neve|snow|nevar/i],['wx','desert',/desert|areia|sand/i],['wx','fog',/neblina|n[eé]voa|fog|mist/i],['wx','clear',/\bsol\b|ensolar|clear|limpo|bom tempo|sunny|\bsun\b/i],
  ['tod','night',/noite|night|escuro|dark/i],['tod','day',/\bdia\b|\bday\b|manh[aã]|morning/i],['fly',/voar|\bfly|drone|de cima|a[eé]rea|bird/i],
  ['job',/quem [eé]|who are you|what do you do|o que (voc[eê]|vc) faz|sua fun/i],['help',/ajuda|help|comando|what can|o que posso/i],['hi',/^\s*(oi|ol[aá]|hello|hi|hey|e a[ií])\b/i],
  ['need',/precis|\bneed|pend|aprov|waiting|espera|fila|queue/i],['status',/status|estado|andamento|como (vai|est)|how.*(going|are)|what.*doing/i],
  ['open',/abr(ir|a|e)|\bopen|ir para|go to|p[aá]gina|\bpage/i],['focus',/onde|where|mostr|\bshow|foc|\bver\b|perto|close|zoom/i]];
const hhmm=d=>d.toTimeString().slice(0,5);

const Chat={log:{},unread:{},typing:false,
  stage:r=>ROLE_STAGE[r],
  name:r=>charName(r),
  avatar(r,cls=''){const a=ART.chars[r];return `<span class="bav ${cls}" style="--sc:${SC[ROLE_STAGE[r]]}">${a?`<img src="${a.src}" alt="">`:ico(ICON_OF(ROLE_STAGE[r]),'width="16" height="16"')}</span>`},
  push(r,who,text,chips){const l=this.log[r]||(this.log[r]=[]);l.push({who,text,chips,ts:new Date()});if(l.length>80)l.shift();if(who==='bot'&&!(Twin.panelOpen()&&S.ptab==='chat'&&S.bot===r))this.unread[r]=(this.unread[r]||0)+1;this.refresh()},
  fromEvent(ev){if(!ev.stage)return;const r=STAGE_ROLE[ev.stage];this.push(r,'bot',phrase(ev))},
  seed(){S.events.slice().reverse().forEach(ev=>{if(ev.stage){const r=STAGE_ROLE[ev.stage],l=this.log[r]||(this.log[r]=[]);l.push({who:'bot',text:phrase(ev),ts:ev.ts})}})},
  open(r){S.bot=r;S.ptab='chat';S.panel=true;this.unread[r]=0;this.greet(r);Twin.update(true)},
  greet(r){const l=this.log[r]||(this.log[r]=[]);if(!l.some(m=>m.who==='sys'))l.unshift({who:'sys',text:t('bot.hi',{name:this.name(r),job:t('bot.'+r+'.job')}),ts:new Date()})},
  chipsFor(){return [t('chip.status'),t('chip.need'),t('chip.show'),t('chip.follow'),t('chip.open'),t('chip.rain'),t('chip.snow'),t('chip.desert'),t('chip.sun'),t('chip.night'),t('chip.fly')]},
  html(){const r=S.bot,st=Twin.statusOf(ROLE_STAGE[r]);this.greet(r);
    return `<div class="chat" id="chat"><div class="bots" role="tablist" aria-label="${t('pn.tab.chat')}">${BOT_ROLES.map(x=>`<button class="bot" role="tab" data-act="bot" data-r="${x}" aria-selected="${x===r}" title="${esc(this.name(x))}" style="--sc:${SC[ROLE_STAGE[x]]}">${this.avatar(x)}${this.unread[x]?`<i class="ud">${this.unread[x]}</i>`:''}</button>`).join('')}</div>
      <div class="bhead">${this.avatar(r,'lg')}<div><b>${esc(this.name(r))}</b><small>${t('station.'+ROLE_STAGE[r])} · <i class="sdot ${st[0]}"></i>${st[1]}</small></div><span class="stc" style="--chipc:#7b5cd6" title="${esc(t('chat.note'))}">${t('chat.free')}</span></div>
      <div class="msgs" id="chatMsgs" aria-live="polite">${this.msgsHTML()}</div>
      <div class="qchips" id="chatChips">${this.chipsFor().map(c=>`<button type="button" class="qc" data-act="chip" data-t="${esc(c)}">${esc(c)}</button>`).join('')}</div>
      <form class="composer" id="chatForm" autocomplete="off"><input id="chatIn" type="text" placeholder="${esc(t('chat.ph',{name:this.name(r)}))}" aria-label="${esc(t('chat.ph',{name:this.name(r)}))}"><button class="tbtn send" type="submit" aria-label="${t('chat.send')}">${ico('publish')}</button></form></div>`},
  msgsHTML(){const r=S.bot,l=this.log[r]||[];return l.slice(-30).map(m=>`<div class="m ${m.who}">${m.who==='bot'||m.who==='sys'?this.avatar(r,'sm'):''}<p>${esc(m.text)}</p><time>${hhmm(m.ts)}</time></div>`).join('')+(this.typing?`<div class="m bot typing">${this.avatar(r,'sm')}<p class="dots"><i></i><i></i><i></i></p></div>`:'')},
  refresh(){const m=document.getElementById('chatMsgs');if(!m||!(S.ptab==='chat'))return;const atEnd=m.scrollHeight-m.scrollTop-m.clientHeight<40||this.typing;m.innerHTML=this.msgsHTML();if(atEnd)m.scrollTop=m.scrollHeight;
    const bots=document.querySelector('#chat .bots');if(bots)bots.querySelectorAll('.bot').forEach(b=>{const r=b.dataset.r,u=this.unread[r];let ud=b.querySelector('.ud');if(u){if(!ud){ud=document.createElement('i');ud.className='ud';b.appendChild(ud)}ud.textContent=u}else if(ud)ud.remove()});Twin.unreadBadge()},
  mount(){const m=document.getElementById('chatMsgs');if(m)m.scrollTop=m.scrollHeight},
  send(text){text=String(text||'').trim().slice(0,240);if(!text)return;const r=S.bot;this.push(r,'me',text);this.typing=true;this.refresh();
    const rep=this.reply(r,text);setTimeout(()=>{this.typing=false;if(rep.action)rep.action();this.push(r,'bot',rep.text)},S.reduce?50:550+Math.min(700,rep.text.length*6))},
  reply(r,txt){const stage=ROLE_STAGE[r],job=t('bot.'+r+'.job');let hit=null;for(const it of INTENTS){const re=it[it.length-1];if(re.test(txt)){hit=it;break}}
    const kind=hit?hit[0]:'';
    if(kind==='wx')return{text:t('bot.r.wx.'+hit[1]),action:()=>{S.wx=hit[1];Scene.applyTod&&Scene.applyTod();Twin.update(true)}};
    if(kind==='tod')return{text:t('bot.r.tod.'+hit[1]),action:()=>{S.tod=hit[1];try{localStorage.setItem('sv.tod',S.tod)}catch(e){}Scene.applyTod&&Scene.applyTod();Twin.update(true)}};
    if(kind==='follow')return{text:t('bot.r.follow'),action:()=>Scene.follow&&Scene.follow(r)};
    if(kind==='stop')return{text:t('bot.r.stop'),action:()=>{if(Scene.follow)Scene.follow(null)}};
    if(kind==='fly')return{text:t('bot.r.fly'),action:()=>Scene.flyOver&&Scene.flyOver()};
    if(kind==='job')return{text:job};
    if(kind==='help')return{text:t('bot.r.help')};
    if(kind==='hi')return{text:t('bot.hi',{name:this.name(r),job})};
    if(kind==='need'){const n=needCount();return{text:n?t('bot.r.need',{n,r:S.queue.length,p:S.pubq.length,f:S.fails.length?t('kpi.need.fail',{f:S.fails.length}):''}):t('bot.r.noneed')}}
    if(kind==='status')return{text:this.status(r)};
    if(kind==='open'){const pg=PAGE_OF[stage];return{text:t('bot.r.open',{page:t('nav.'+pg)}),action:()=>setTimeout(()=>go(pg),700)}}
    if(kind==='focus')return{text:t('bot.r.focus',{b:t('bld.'+BLD_OF[stage])}),action:()=>{S.sel=stage;S.panel=true;Twin.update(true)}};
    return{text:t('bot.r.fallback',{job})}},
  status(r){const it=Twin.tracked();
    if(r==='brander')return t('bot.st.brander',{v:FACTS.filter(f=>f.v).length,t:FACTS.length});
    if(r==='ideator')return t('bot.st.ideator');
    if(r==='director'){const m=Twin.rows('make')[0];const p=parseInt(m.v)||0;return p>0&&p<100?t('bot.st.director',{p}):t('bot.st.director.idle')}
    if(r==='gatekeeper')return S.queue.length?t('bot.st.gatekeeper',{n:S.queue.length}):t('bot.st.gatekeeper.none');
    if(r==='poster')return t('bot.st.poster',{n:S.pubq.length,d:S.done});
    if(r==='analyst')return t('bot.st.analyst');
    if(r==='reflector')return t('bot.st.reflector',{c:SIM.cycle,f:t('fam.tip')});
    return t('bot.st.evolver')}
};
