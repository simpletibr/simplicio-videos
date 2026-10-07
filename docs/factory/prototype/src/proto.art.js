/* ===== art: icons, themes, characters, kiosks, scenes (all original flat-vector shapes) ===== */
const ROLES=['brander','ideator','director','gatekeeper','poster','analyst','reflector','evolver'];
const STAGES=['brand','ideas','make','review','publish','metrics','report'];
const STAGE_ROLE={brand:'brander',ideas:'ideator',make:'director',review:'gatekeeper',publish:'poster',metrics:'analyst',report:'reflector'};

const ICON={
  factory:'<rect x="3" y="14" width="18" height="5" rx="2.5"/><circle cx="7.5" cy="16.5" r=".8"/><circle cx="12" cy="16.5" r=".8"/><circle cx="16.5" cy="16.5" r=".8"/><rect x="6" y="6" width="5" height="6" rx="1"/><path d="M14 12V8h4v4"/>',
  inbox:'<path d="M6 17v-6a6 6 0 0112 0v6l1.5 2h-15z"/><path d="M10 21h4"/>',
  brand:'<circle cx="12" cy="12" r="8.5"/><circle cx="8.5" cy="10" r="1.2"/><circle cx="12" cy="7.8" r="1.2"/><circle cx="15.5" cy="10" r="1.2"/><path d="M12 20.5c-1.8 0-2.2-1.4-1.4-2.6.8-1.1.2-2.4-1.2-2.4H8"/>',
  ideas:'<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0012 3z"/>',
  studio:'<rect x="3.5" y="9" width="17" height="11" rx="1.5"/><path d="M3.5 9l2.5-5h3.5l-2.5 5M10 9l2.5-5H16l-2.5 5M16.5 9L19 4h1.5l-.5 5"/>',
  review:'<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  publish:'<path d="M3 11l18-8-8 18-2.5-7.5z"/><path d="M10.5 13.5L21 3"/>',
  metrics:'<path d="M5 20v-9M12 20V4M19 20v-8"/>',
  report:'<path d="M6 3h12v18H6zM9 8h6M9 12h6M9 16h4"/>',
  activity:'<path d="M3 12h4l2.5-7 4 14 2.5-7H21"/>',
  settings:'<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  more:'<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  alert:'<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.4"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.4"/>',
  check:'<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  lock:'<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
  pause:'<path d="M8 5v14M16 5v14"/>',
  play:'<path d="M8 5l11 7-11 7z" fill="currentColor"/>',
  stop:'<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  fail:'<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>'
};
const ico=(n,x='')=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${x}>${ICON[n]}</svg>`;

function shade(hex,a){const n=parseInt(hex.slice(1),16);let r=n>>16,g=n>>8&255,b=n&255;const f=v=>Math.max(0,Math.min(255,Math.round(a<0?v*(1+a):v+(255-v)*a)));return '#'+[f(r),f(g),f(b)].map(v=>v.toString(16).padStart(2,'0')).join('')}

/* ---------- themes (br is the MVP theme; the rest are concepts that show the format) ---------- */
const grad=(id,a,b)=>`<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>`;
const star=(x,y,r,f)=>{let d='';for(let i=0;i<10;i++){const a=-Math.PI/2+i*Math.PI/5,rr=i%2?r*.45:r;d+=(i?'L':'M')+(x+Math.cos(a)*rr).toFixed(1)+' '+(y+Math.sin(a)*rr).toFixed(1)}return `<path d="${d}Z" fill="${f}"/>`};
const hills=(W,H,c1,c2)=>`<path d="M0 ${H*.8} C ${W*.2} ${H*.72}, ${W*.35} ${H*.86}, ${W*.55} ${H*.8} S ${W*.9} ${H*.74}, ${W} ${H*.82} V${H} H0Z" fill="${c1}"/><path d="M0 ${H*.88} C ${W*.25} ${H*.82}, ${W*.5} ${H*.93}, ${W*.75} ${H*.87} S ${W*.95} ${H*.9}, ${W} ${H*.88} V${H} H0Z" fill="${c2}"/>`;
const cloud=(x,y,s,f='#fff',o=.9)=>`<g transform="translate(${x} ${y}) scale(${s})" fill="${f}" opacity="${o}"><ellipse cx="0" cy="0" rx="46" ry="16"/><ellipse cx="-22" cy="-12" rx="22" ry="16"/><ellipse cx="14" cy="-16" rx="26" ry="19"/></g>`;
const pat=(id,w,h,inner)=>`<pattern id="${id}" width="${w}" height="${h}" patternUnits="userSpaceOnUse">${inner}</pattern>`;
const band=(W,H,id,hh,edge)=>`<rect x="0" y="${H-hh}" width="${W}" height="${hh}" fill="url(#${id})"/><rect x="0" y="${H-hh-4}" width="${W}" height="5" fill="${edge}"/>`;

const TH={
 br:{id:'br',status:'mvp',name:{en:'Brazil',pt:'Brasil'},tag:{en:'Tropical leaves, tiles and bunting',pt:'Folhagem, azulejos e bandeirinhas'},
  p:{sky1:'#8fd8ff',sky2:'#effbff',belt:'#2b3a32',line:'#e8f1ea',roof:'#1f6feb',wall:'#fff3c4',ink:'#10321f',body:'#2aa05a',head:'#ffe39a',accent:'#ffd23f',gate:'#e5483b'},
  badge:(p)=>`<g transform="translate(0 -24)"><circle r="7.5" fill="#fff" stroke="${p.ink}" stroke-width="1.6"/><circle r="3" fill="#2a62c9"/><circle cx="-5" r="1.6" fill="#2a62c9"/><circle cx="5" r="1.6" fill="#2a62c9"/><circle cy="-5" r="1.6" fill="#2a62c9"/><circle cy="5" r="1.6" fill="#2a62c9"/></g>`,
  decor:(W,H,u)=>{const leaf=(x,y,s,r,c)=>`<g transform="translate(${x} ${y}) rotate(${r}) scale(${s})"><path d="M0 0C20 -52 92 -72 152 -30 100 -36 60 -20 0 0Z" fill="${c}"/><path d="M0 0L118 -34" stroke="#1c6a3a" stroke-width="3" fill="none"/></g>`;
   let b=`<path d="M0 26 Q${W/2} 74 ${W} 26" fill="none" stroke="#6b4a2a" stroke-width="2"/>`;const cs=['#ffd23f','#1f8f4b','#2a62c9','#ffffff'],n=Math.round(W/68);
   for(let i=0;i<n;i++){const x=(i+.5)*W/n,t=x/W,y=26+96*t*(1-t);b+=`<path d="M${x-14} ${y} L${x+14} ${y} L${x} ${y+30}Z" fill="${cs[i%4]}" stroke="#10321f" stroke-width="1.2"/>`}
   return `<defs>${grad('sk'+u,'#8fd8ff','#effbff')}${pat('az'+u,46,46,'<rect width="46" height="46" fill="#f7fbff"/><g fill="#2a62c9"><circle cx="12" cy="23" r="9"/><circle cx="34" cy="23" r="9"/><circle cx="23" cy="12" r="9"/><circle cx="23" cy="34" r="9"/></g><circle cx="23" cy="23" r="6" fill="#f7fbff"/><circle cx="23" cy="23" r="2.6" fill="#ffd23f"/>')}</defs>
   <rect width="${W}" height="${H}" fill="url(#sk${u})"/><circle cx="${W*.1}" cy="${H*.2}" r="${H*.15}" fill="#ffe27a" opacity=".35"/><circle cx="${W*.1}" cy="${H*.2}" r="${H*.1}" fill="#ffe27a"/>${cloud(W*.62,H*.16,1.2)}${cloud(W*.84,H*.26,.9)}
   ${hills(W,H,'#35a35f','#2b8a4e')}${band(W,H,'az'+u,56,'#ffd23f')}${b}
   ${leaf(W*.015,H*.99,1.15,-18,'#1f8f4b')}${leaf(W*.045,H*.99,.95,-52,'#2fae5f')}${leaf(W*.985,H*.99,1.15,198,'#1f8f4b')}${leaf(W*.955,H*.99,.95,232,'#2fae5f')}`}},
 cn:{id:'cn',status:'concept',name:{en:'China',pt:'China'},tag:{en:'Lanterns and lattice windows',pt:'Lanternas e janelas de treliça'},
  p:{sky1:'#b31220',sky2:'#5a0710',belt:'#2a1114',line:'#f5d77a',roof:'#c8102e',wall:'#fff0d0',ink:'#3d0a10',body:'#d62839',head:'#ffe1a8',accent:'#f5c542',gate:'#f5c542'},
  badge:(p)=>`<g transform="translate(0 -26)"><circle r="6" fill="${p.accent}" stroke="${p.ink}" stroke-width="1.5"/><path d="M-3 6L-5 15M0 6V16M3 6L5 15" stroke="${p.accent}" stroke-width="2" fill="none"/></g>`,
  decor:(W,H,u)=>{const lan=(x,len,s)=>`<g transform="translate(${x} 0)"><line x1="0" y1="0" x2="0" y2="${len}" stroke="#f5c542" stroke-width="2"/><g transform="translate(0 ${len}) scale(${s})"><rect x="-10" y="-4" width="20" height="8" rx="2" fill="#f5c542"/><ellipse cx="0" cy="28" rx="28" ry="26" fill="#e0212f" stroke="#f5c542" stroke-width="2.5"/><path d="M-14 6Q0 28-14 50M14 6Q0 28 14 50M0 2V54" stroke="#a80f1b" stroke-width="2" fill="none"/><rect x="-9" y="52" width="18" height="6" rx="2" fill="#f5c542"/><path d="M0 58V82M-5 58L-7 78M5 58L7 78" stroke="#f5c542" stroke-width="2.4" fill="none"/></g></g>`;
   let ls='';const n=Math.max(4,Math.round(W/150));for(let i=0;i<n;i++)ls+=lan((i+.5)*W/n,16+((i*37)%46),.85+((i%3)*.1));
   return `<defs>${grad('sk'+u,'#b31220','#5a0710')}${pat('lt'+u,44,44,'<rect width="44" height="44" fill="#470a10"/><path d="M22 3L41 22 22 41 3 22Z" fill="none" stroke="#f5c542" stroke-width="2"/><circle cx="22" cy="22" r="3" fill="#f5c542"/>')}</defs>
   <rect width="${W}" height="${H}" fill="url(#sk${u})"/><g fill="none" stroke="#f5c542" stroke-width="3" opacity=".42"><path d="M${W*.1} ${H*.62}a26 26 0 1 1 52 0a19 19 0 1 1 38 0"/><path d="M${W*.72} ${H*.5}a26 26 0 1 1 52 0a19 19 0 1 1 38 0"/><path d="M${W*.42} ${H*.7}a22 22 0 1 1 44 0a16 16 0 1 1 32 0"/></g>
   <circle cx="${W*.86}" cy="${H*.2}" r="${H*.09}" fill="#f5c542" opacity=".9"/>${hills(W,H,'#7a0c16','#4a0a10')}${band(W,H,'lt'+u,56,'#f5c542')}${ls}`}},
 us:{id:'us',status:'concept',name:{en:'United States',pt:'Estados Unidos'},tag:{en:'Retro diner, neon and checker floor',pt:'Lanchonete retrô, neon e piso xadrez'},
  p:{sky1:'#6ec1ff',sky2:'#eaf7ff',belt:'#2c2f36',line:'#fff',roof:'#d92d2d',wall:'#fff8ea',ink:'#1b2a5c',body:'#2a5bd7',head:'#ffe8c9',accent:'#ffcf3f',gate:'#d92d2d'},
  badge:(p)=>`<g transform="translate(0 -24)">${star(0,0,8,'#fff')}</g>`,
  decor:(W,H,u)=>{let st='';for(let i=0;i<7;i++)st+=star(W*(.1+i*.13),H*(.1+((i*29)%18)/100),5,'#fff');
   return `<defs>${grad('sk'+u,'#6ec1ff','#eaf7ff')}${pat('ck'+u,44,44,'<rect width="44" height="44" fill="#fff"/><rect width="22" height="22" fill="#1b2a5c"/><rect x="22" y="22" width="22" height="22" fill="#1b2a5c"/>')}${pat('aw'+u,60,40,'<rect width="60" height="40" fill="#fff"/><rect width="30" height="40" fill="#d92d2d"/>')}</defs>
   <rect width="${W}" height="${H}" fill="url(#sk${u})"/>${cloud(W*.2,H*.2,1.3)}${cloud(W*.7,H*.14,1)}${st}
   <rect x="0" y="0" width="${W}" height="44" fill="url(#aw${u})"/><path d="M0 44h${W}" stroke="#1b2a5c" stroke-width="3"/>
   <g transform="translate(${W*.76} ${H*.22})"><rect x="-64" y="-26" width="128" height="52" rx="12" fill="#1b2a5c" stroke="#ff4d6d" stroke-width="5"/><text x="0" y="9" text-anchor="middle" font-size="28" fill="#ff8aa1" stroke="#ff4d6d" stroke-width="1.2" style="paint-order:normal">OPEN</text></g>
   ${hills(W,H,'#bfe3b0','#9fd08f')}${band(W,H,'ck'+u,56,'#d92d2d')}`}},
 ru:{id:'ru',status:'concept',name:{en:'Russia',pt:'Rússia'},tag:{en:'Onion domes and folk florals, winter night',pt:'Cúpulas e padrões florais, noite de inverno'},
  p:{sky1:'#24366f',sky2:'#0b1230',belt:'#2b2f45',line:'#f0d36b',roof:'#b3262d',wall:'#fff1d6',ink:'#241a3a',body:'#c62d3a',head:'#ffe6c2',accent:'#d9a441',gate:'#f0d36b'},
  badge:(p)=>`<g transform="translate(0 -24)">${[0,1,2,3,4,5].map(i=>`<circle cx="${Math.cos(i*1.047)*5.5}" cy="${Math.sin(i*1.047)*5.5}" r="3.2" fill="${p.accent}"/>`).join('')}<circle r="2.6" fill="${p.ink}"/></g>`,
  decor:(W,H,u)=>{const dome=(x,y,s,c)=>`<g transform="translate(${x} ${y}) scale(${s})"><rect x="-26" y="0" width="52" height="70" fill="#e9d9bd"/><path d="M-34 0C-34-26-8-30 0-62 8-30 34-26 34 0Z" fill="${c}" stroke="#241a3a" stroke-width="2"/><path d="M0-62V-82M-6-74h12" stroke="#d9a441" stroke-width="3"/></g>`;
   let sn='';for(let i=0;i<46;i++)sn+=`<circle cx="${(i*97)%W}" cy="${(i*53)%(H*.8)}" r="${1+(i%3)*.7}" fill="#fff" opacity=".7"/>`;
   return `<defs>${grad('sk'+u,'#24366f','#0b1230')}${pat('kh'+u,60,56,'<rect width="60" height="56" fill="#1a1328"/><g fill="#c62d3a"><circle cx="30" cy="28" r="9"/></g><g fill="#d9a441"><circle cx="30" cy="12" r="5"/><circle cx="30" cy="44" r="5"/><circle cx="14" cy="28" r="5"/><circle cx="46" cy="28" r="5"/></g><path d="M0 28Q8 14 14 28T30 28M30 28Q38 42 46 28T60 28" stroke="#5aa85a" stroke-width="2" fill="none"/>')}</defs>
   <rect width="${W}" height="${H}" fill="url(#sk${u})"/>${sn}<circle cx="${W*.88}" cy="${H*.16}" r="${H*.07}" fill="#f6f1d6"/>
   ${dome(W*.18,H*.5,.9,'#c62d3a')}${dome(W*.5,H*.46,1.1,'#2a62c9')}${dome(W*.8,H*.5,.85,'#d9a441')}
   <path d="M0 ${H*.84} Q${W*.3} ${H*.78} ${W*.55} ${H*.84} T${W} ${H*.82} V${H} H0Z" fill="#e8edf8"/>${band(W,H,'kh'+u,56,'#d9a441')}`}},
 jp:{id:'jp',status:'concept',name:{en:'Japan',pt:'Japão'},tag:{en:'Cherry blossom, red sun and wave pattern',pt:'Cerejeiras, sol vermelho e ondas'},
  p:{sky1:'#ffe3ee',sky2:'#fff9fb',belt:'#2f3150',line:'#fff',roof:'#cf3d4f',wall:'#fff7f3',ink:'#2a2a4a',body:'#3a4aa0',head:'#ffeadf',accent:'#e86b8c',gate:'#cf3d4f'},
  badge:(p)=>`<g transform="translate(0 -24)">${[0,1,2,3,4].map(i=>`<circle cx="${Math.cos(i*1.2566-1.57)*5.5}" cy="${Math.sin(i*1.2566-1.57)*5.5}" r="3.6" fill="#ff9ab7"/>`).join('')}<circle r="2" fill="#ffe27a"/></g>`,
  decor:(W,H,u)=>{let pt='';for(let i=0;i<26;i++)pt+=`<circle cx="${(i*131)%W}" cy="${30+(i*71)%(H*.7)}" r="${3+(i%3)}" fill="#ffb3c8" opacity=".85"/>`;
   return `<defs>${grad('sk'+u,'#ffe3ee','#fff9fb')}${pat('sg'+u,48,26,'<rect width="48" height="26" fill="#21377a"/><g fill="none" stroke="#9fb4ee" stroke-width="2"><circle cx="24" cy="26" r="22"/><circle cx="24" cy="26" r="15"/><circle cx="24" cy="26" r="8"/><circle cx="0" cy="13" r="22"/><circle cx="0" cy="13" r="15"/><circle cx="48" cy="13" r="22"/><circle cx="48" cy="13" r="15"/></g>')}</defs>
   <rect width="${W}" height="${H}" fill="url(#sk${u})"/><circle cx="${W*.82}" cy="${H*.22}" r="${H*.12}" fill="#d6283f"/>
   <path d="M0 ${H*.2} C ${W*.08} ${H*.12}, ${W*.16} ${H*.28}, ${W*.3} ${H*.1}" stroke="#6b4a3a" stroke-width="8" fill="none" stroke-linecap="round"/>${pt}
   ${hills(W,H,'#f7c8d8','#efb2c6')}${band(W,H,'sg'+u,56,'#e86b8c')}`}},
 dragons:{id:'dragons',status:'concept',name:{en:'Dragons',pt:'Dragões'},tag:{en:'Dusk mountains and a dragon in flight',pt:'Montanhas ao anoitecer e um dragão em voo'},
  p:{sky1:'#2a1458',sky2:'#e8742b',belt:'#2b2140',line:'#ffb347',roof:'#7b3fe4',wall:'#3a2a5e',ink:'#140a2e',body:'#7b3fe4',head:'#d9c7ff',accent:'#ff8a3d',gate:'#ff8a3d'},
  badge:(p)=>`<g transform="translate(0 -24)"><path d="M-7 4Q-7-6 0-7 7-6 7 4Q0 0-7 4Z" fill="${p.accent}" stroke="${p.ink}" stroke-width="1.4"/></g>`,
  decor:(W,H,u)=>{let em='';for(let i=0;i<30;i++)em+=`<circle cx="${(i*113)%W}" cy="${H*.35+(i*61)%(H*.5)}" r="${1.4+(i%3)}" fill="#ffb347" opacity=".75"/>`;
   return `<defs>${grad('sk'+u,'#2a1458','#e8742b')}</defs><rect width="${W}" height="${H}" fill="url(#sk${u})"/><circle cx="${W*.16}" cy="${H*.2}" r="${H*.09}" fill="#ffe8b8"/>
   <path d="M0 ${H*.74} L${W*.1} ${H*.5} L${W*.18} ${H*.62} L${W*.3} ${H*.4} L${W*.42} ${H*.66} L${W*.55} ${H*.46} L${W*.68} ${H*.7} L${W*.8} ${H*.48} L${W*.92} ${H*.64} L${W} ${H*.52} V${H} H0Z" fill="#1d0f3e"/>
   <g transform="translate(${W*.68} ${H*.16}) scale(${H/560})" fill="#14082c"><path d="M0 40C30 20 60 0 110 -10 90 6 80 20 90 30 70 24 50 34 30 52 40 60 20 66 0 40Z"/><path d="M20 38C10 0 40-30 90-44 70-20 66-6 76 8 56 0 36 10 20 38Z"/><path d="M-26 60L0 44 6 56Z"/><circle cx="104" cy="-4" r="3" fill="#ffb347"/></g>${em}${hills(W,H,'#2a1850','#1a0f33')}
   <rect x="0" y="${H-56}" width="${W}" height="56" fill="#140a2e"/><rect x="0" y="${H-60}" width="${W}" height="5" fill="#ff8a3d"/>`}},
 realms:{id:'realms',status:'concept',name:{en:'Realms',pt:'Reinos'},tag:{en:'A hilltop castle with banners and torches',pt:'Um castelo no alto da colina com estandartes'},
  p:{sky1:'#9fb4c7',sky2:'#e8eef3',belt:'#35353c',line:'#d9d3c1',roof:'#8a1f2b',wall:'#d9d3c1',ink:'#25252d',body:'#5a6f8f',head:'#eadfc6',accent:'#c9a227',gate:'#c9a227'},
  badge:(p)=>`<g transform="translate(0 -26)"><path d="M-7 -6H7V3Q7 10 0 13 -7 10 -7 3Z" fill="${p.accent}" stroke="${p.ink}" stroke-width="1.5"/><path d="M0-6V13" stroke="${p.ink}" stroke-width="1.4"/></g>`,
  decor:(W,H,u)=>{const castle=(x,y,s)=>`<g transform="translate(${x} ${y}) scale(${s})" fill="#6a6d78" stroke="#25252d" stroke-width="2"><rect x="-90" y="-60" width="180" height="90"/><rect x="-110" y="-110" width="44" height="140"/><rect x="66" y="-110" width="44" height="140"/><rect x="-22" y="-150" width="44" height="180"/>${[-110,-98,-86,66,78,90,-22,-10,2,14].map((cx,i)=>`<rect x="${cx}" y="${i<6?-124:-164}" width="8" height="14"/>`).join('')}<path d="M-14 30V-8Q0-24 14-8V30Z" fill="#25252d"/><path d="M0-164V-196L26-186 0-176" fill="#8a1f2b"/></g>`;
   const ban=(x,y,c)=>`<g transform="translate(${x} ${y})"><line x1="0" y1="-8" x2="0" y2="0" stroke="#25252d" stroke-width="3"/><path d="M-18 0H18V54L0 42-18 54Z" fill="${c}" stroke="#25252d" stroke-width="2"/><circle cx="0" cy="20" r="7" fill="#c9a227" stroke="#25252d" stroke-width="1.6"/></g>`;
   return `<defs>${grad('sk'+u,'#9fb4c7','#e8eef3')}</defs><rect width="${W}" height="${H}" fill="url(#sk${u})"/>${cloud(W*.2,H*.18,1.2,'#fff',.8)}${cloud(W*.8,H*.24,1,'#fff',.8)}
   <path d="M${W*.2} ${H*.82} Q${W*.5} ${H*.4} ${W*.8} ${H*.82}Z" fill="#6d7a62"/>${castle(W*.5,H*.62,Math.min(W,H*1.6)/1280*1.1)}
   ${ban(W*.1,0,'#8a1f2b')}${ban(W*.9,0,'#2d4a8a')}${ban(W*.3,0,'#c9a227')}${ban(W*.7,0,'#8a1f2b')}${hills(W,H,'#7d8a70','#5f6a55')}
   <rect x="0" y="${H-56}" width="${W}" height="56" fill="#4a4a54"/><rect x="0" y="${H-60}" width="${W}" height="5" fill="#c9a227"/>`}},
 courtyard:{id:'courtyard',status:'concept',name:{en:'Courtyard',pt:'Pátio'},tag:{en:'A sunny neighborhood courtyard with a laundry line',pt:'Um pátio de vizinhança ensolarado com varal'},
  p:{sky1:'#ffe7b3',sky2:'#fff6dd',belt:'#4a3328',line:'#f0dfc2',roof:'#b8472a',wall:'#f4d6a0',ink:'#3a1f12',body:'#e0753a',head:'#ffe4c2',accent:'#e85d2a',gate:'#2f6fda'},
  badge:(p)=>`<g transform="translate(0 -40)"><rect x="-15" y="0" width="30" height="7" fill="#2f6fda"/></g>`,
  decor:(W,H,u)=>{const door=(x,c)=>`<g transform="translate(${x} ${H*.34})"><rect x="-34" y="0" width="68" height="${H*.4}" rx="6" fill="${c}" stroke="#3a1f12" stroke-width="3"/><rect x="-22" y="14" width="44" height="${H*.14}" rx="4" fill="rgba(255,255,255,.25)"/><circle cx="20" cy="${H*.22}" r="4" fill="#f5c542"/></g>`;
   let cl='';const cs=['#2f6fda','#fff','#e85d2a','#f5c542','#2f9a5a'];for(let i=0;i<8;i++){const x=W*.1+i*(W*.8/8),t=(x-W*.1)/(W*.8);cl+=`<rect x="${x}" y="${H*.2+30*Math.sin(t*3.14)+8}" width="30" height="34" fill="${cs[i%5]}" stroke="#3a1f12" stroke-width="1.5"/>`}
   return `<defs>${grad('sk'+u,'#ffe7b3','#fff6dd')}${pat('br'+u,60,28,'<rect width="60" height="28" fill="#c5724b"/><rect x="1" y="1" width="28" height="12" fill="#d6845a"/><rect x="31" y="15" width="28" height="12" fill="#d6845a"/>')}</defs>
   <rect width="${W}" height="${H}" fill="url(#sk${u})"/><rect x="0" y="${H*.14}" width="${W}" height="${H*.7}" fill="url(#br${u})"/>${door(W*.16,'#2f6fda')}${door(W*.5,'#2f9a5a')}${door(W*.84,'#e85d2a')}
   <path d="M${W*.06} ${H*.2} Q${W*.5} ${H*.3} ${W*.94} ${H*.2}" stroke="#3a1f12" stroke-width="2.5" fill="none"/>${cl}
   <g transform="translate(${W*.34} ${H*.8})"><ellipse cx="0" cy="0" rx="34" ry="12" fill="#8a5a36"/><rect x="-34" y="-50" width="68" height="50" fill="#a9703f"/><ellipse cx="0" cy="-50" rx="34" ry="12" fill="#c58a52"/><path d="M-34-30H34M-34-12H34" stroke="#3a1f12" stroke-width="3"/></g>
   <g transform="translate(${W*.68} ${H*.82})"><path d="M-22 0L-16-34H16L22 0Z" fill="#b8472a"/><path d="M0-34V-62M0-46Q-18-52-20-66M0-50Q16-56 20-70" stroke="#2f9a5a" stroke-width="5" fill="none"/></g>
   <rect x="0" y="${H-52}" width="${W}" height="52" fill="#8a5a36"/><rect x="0" y="${H-56}" width="${W}" height="5" fill="#e85d2a"/>`}},
 tiny:{id:'tiny',status:'concept',name:{en:'Tiny Workers',pt:'Mini Operários'},tag:{en:'Pastel hills, clouds and little gears',pt:'Colinas pastel, nuvens e engrenagens'},
  p:{sky1:'#d9f7ee',sky2:'#fff4ec',belt:'#4b5563',line:'#fff',roof:'#ff9bb3',wall:'#ffffff',ink:'#2d3b45',body:'#4cc3a5',head:'#fff1de',accent:'#ffb86b',gate:'#ff7b9c'},
  badge:(p)=>`<g transform="translate(0 -40)"><path d="M0 4L-12-4V12ZM0 4L12-4V12Z" fill="#ff9bb3" stroke="${p.ink}" stroke-width="1.4"/><circle cx="0" cy="4" r="3" fill="#ff7b9c"/></g>`,
  decor:(W,H,u)=>{const gear=(x,y,r,c)=>{let t='';for(let i=0;i<10;i++)t+=`<rect x="${-r*.16}" y="${-r*1.22}" width="${r*.32}" height="${r*.36}" rx="2" transform="rotate(${i*36})"/>`;return `<g transform="translate(${x} ${y})" fill="${c}" opacity=".85">${t}<circle r="${r}"/><circle r="${r*.42}" fill="#fff"/></g>`};
   return `<defs>${grad('sk'+u,'#d9f7ee','#fff4ec')}</defs><rect width="${W}" height="${H}" fill="url(#sk${u})"/>${cloud(W*.2,H*.18,1.4)}${cloud(W*.62,H*.12,1.1)}${cloud(W*.86,H*.28,1.3)}
   <g fill="none" stroke-width="12" opacity=".5"><path d="M${W*.62} ${H*.46} a110 110 0 0 1 220 0" stroke="#ffb3c8"/><path d="M${W*.62+12} ${H*.46} a98 98 0 0 1 196 0" stroke="#ffe0a3"/><path d="M${W*.62+24} ${H*.46} a86 86 0 0 1 172 0" stroke="#bfe8d8"/></g>
   ${gear(W*.08,H*.22,34,'#ffb86b')}${gear(W*.14,H*.3,22,'#ff9bb3')}${gear(W*.93,H*.5,30,'#7fd6c1')}${hills(W,H,'#bfe8d8','#a5dcc9')}
   <rect x="0" y="${H-52}" width="${W}" height="52" fill="#9fd6c4"/><rect x="0" y="${H-56}" width="${W}" height="5" fill="#ffb86b"/>`}}
};
const THEME_ORDER=['br','us','cn','ru','jp','dragons','realms','courtyard','tiny'];

/* ---------- characters ---------- */
function charSVG(role,th){
  const p=th.p,ink=p.ink,body=p.body,head=p.head,dark=shade(body,-.25);let acc='',top='';
  const ant=`<line x1="0" y1="-80" x2="0" y2="-88" stroke="${ink}" stroke-width="2"/><circle cx="0" cy="-90" r="3.4" fill="${p.accent}" stroke="${ink}" stroke-width="1.4"/>`;
  if(role==='brander'){acc=`<g><path d="M24 -26L38 -50" stroke="${ink}" stroke-width="3" stroke-linecap="round"/><ellipse cx="39.5" cy="-53" rx="4.5" ry="6" fill="${p.accent}" stroke="${ink}" stroke-width="1.6" transform="rotate(25 39.5 -53)"/></g><circle cx="-22" cy="-24" r="7" fill="${p.accent}" stroke="${ink}" stroke-width="1.6"/>`;top=ant}
  else if(role==='ideator'){top=`<line x1="0" y1="-80" x2="0" y2="-86" stroke="${ink}" stroke-width="2"/><circle cx="0" cy="-95" r="8.5" fill="#ffe27a" stroke="${ink}" stroke-width="1.8"/><path d="M-13 -99l-6 -2M13 -99l6 -2M0 -108v-6" stroke="${p.accent}" stroke-width="2" stroke-linecap="round"/>`}
  else if(role==='director'){acc=`<g transform="translate(25 -38) rotate(-12)"><rect x="0" y="4" width="22" height="14" rx="2" fill="${ink}"/><rect x="0" y="-3" width="22" height="7" rx="2" fill="#fff" stroke="${ink}" stroke-width="1.6"/><path d="M4 -3l4 7M11 -3l4 7M18 -3l3 7" stroke="${ink}" stroke-width="1.6"/></g>`;top=ant}
  else if(role==='gatekeeper'){top=`<path d="M-21 -78Q0 -106 21 -78Z" fill="#ffd23f" stroke="${ink}" stroke-width="2"/><rect x="-24" y="-80" width="48" height="5" rx="2.5" fill="#ffd23f" stroke="${ink}" stroke-width="2"/>`;acc=`<line x1="34" y1="0" x2="34" y2="-52" stroke="${ink}" stroke-width="3"/><circle cx="34" cy="-62" r="11" fill="${p.gate}" stroke="${ink}" stroke-width="2"/><rect x="27" y="-64" width="14" height="4" rx="1" fill="#fff"/>`}
  else if(role==='poster'){acc=`<g transform="translate(24 -34) rotate(-18)"><path d="M0 -6L22 -14V14L0 6Z" fill="${p.accent}" stroke="${ink}" stroke-width="1.8"/><rect x="-8" y="-6" width="9" height="12" rx="2" fill="${ink}"/></g>`;top=ant}
  else if(role==='analyst'){acc=`<circle cx="35" cy="-46" r="9" fill="rgba(255,255,255,.65)" stroke="${ink}" stroke-width="2.4"/><path d="M41.500 -39.500L49 -32" stroke="${ink}" stroke-width="3.2" stroke-linecap="round"/><path d="M-8 -14v-8M-2 -14v-14M4 -14v-10" stroke="#fff" stroke-width="3" stroke-linecap="round"/>`;top=ant}
  else if(role==='reflector'){acc=`<ellipse cx="35" cy="-42" rx="9" ry="12" fill="#cfeaff" stroke="${ink}" stroke-width="2"/><path d="M31 -48q4 -4 8 0" stroke="#fff" stroke-width="2" fill="none"/><path d="M35 -30L35 -22" stroke="${ink}" stroke-width="3"/>`;top=ant}
  else {top=`<path d="M0 -80V-92" stroke="${ink}" stroke-width="2.4"/><path d="M0 -92q-12 -2 -14 -12q10 0 14 12z" fill="#5cc66b" stroke="${ink}" stroke-width="1.6"/><path d="M0 -92q12 -2 14 -12q-10 0 -14 12z" fill="#7fd98a" stroke="${ink}" stroke-width="1.6"/>`}
  const leg=`<rect x="-12" y="-9" width="9" height="10" rx="3" fill="${dark}" stroke="${ink}" stroke-width="1.6"/><rect x="3" y="-9" width="9" height="10" rx="3" fill="${dark}" stroke="${ink}" stroke-width="1.6"/>`;
  return `<g class="char"><ellipse cx="0" cy="1" rx="22" ry="4.5" fill="rgba(0,0,0,.22)"/>${leg}<rect x="-24" y="-38" width="9" height="20" rx="4.5" fill="${body}" stroke="${ink}" stroke-width="1.8"/><rect x="15" y="-38" width="9" height="20" rx="4.5" fill="${body}" stroke="${ink}" stroke-width="1.8"/><rect x="-15" y="-44" width="30" height="38" rx="11" fill="${body}" stroke="${ink}" stroke-width="2"/>${th.badge(p)}<rect x="-19" y="-82" width="38" height="38" rx="14" fill="${head}" stroke="${ink}" stroke-width="2"/><circle cx="-7" cy="-64" r="3.4" fill="${ink}"/><circle cx="7" cy="-64" r="3.4" fill="${ink}"/><path d="M-5 -55Q0 -51 5 -55" stroke="${ink}" stroke-width="2" fill="none" stroke-linecap="round"/>${acc}${top}</g>`;
}
function kioskSVG(stage,th,w,h,wallY,x,iconOnly){
  const p=th.p,ink=p.ink,cx=x+w/2;
  return `<g><rect x="${x}" y="${wallY}" width="${w}" height="${h}" rx="9" fill="${p.wall}" stroke="${ink}" stroke-width="3"/>
  <path d="M${x-9} ${wallY+2}L${x+w+9} ${wallY+2}L${x+w-4} ${wallY-26}L${x+4} ${wallY-26}Z" fill="${p.roof}" stroke="${ink}" stroke-width="3" stroke-linejoin="round"/>
  <rect x="${x-3}" y="${wallY-1}" width="${w+6}" height="7" rx="3" fill="${p.accent}" stroke="${ink}" stroke-width="2"/>
  <circle cx="${cx}" cy="${wallY+h/2+6}" r="25" fill="#fff" stroke="${ink}" stroke-width="2.4"/>
  <g transform="translate(${cx-17} ${wallY+h/2-11}) scale(1.42)" fill="none" stroke="${ink}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICON[stage==='brand'?'brand':stage==='ideas'?'ideas':stage==='make'?'studio':stage==='review'?'review':stage==='publish'?'publish':stage==='metrics'?'metrics':'report']}</g></g>`;
}

/* ---------- scene geometry ---------- */
const GEO={
 landscape:{vb:[1280,780],path:'M260 250H1020A110 110 0 0 1 1130 360V490A110 110 0 0 1 1020 600H260A110 110 0 0 1 150 490V360A110 110 0 0 1 260 250Z',
  st:{brand:[330,250,'top'],ideas:[520,250,'top'],make:[710,250,'top'],review:[900,250,'top'],publish:[1130,425,'right'],metrics:[880,600,'bottom'],report:[560,600,'bottom']},bin:[150,425]},
 portrait:{vb:[720,1200],path:'M250 250H410A100 100 0 0 1 510 350V930A100 100 0 0 1 410 1030H250A100 100 0 0 1 150 930V350A100 100 0 0 1 250 250Z',
  st:{brand:[250,250,'top'],ideas:[410,250,'top'],make:[510,490,'right'],review:[510,750,'right'],publish:[410,1030,'bottom'],metrics:[250,1030,'bottom'],report:[150,640,'left']},bin:[150,420]}
};
function place(side,sx,sy){ // kiosk wall rect, label, character feet
  const w=104,h=84;
  if(side==='top'){const ky=sy-34-h;return{kx:sx-w/2,ky,cx:sx+70,cy:sy-30,lx:sx,ly:ky-32}}
  if(side==='bottom'){const ky=sy+60;return{kx:sx-w/2,ky,cx:sx-76,cy:sy+142,lx:sx,ly:ky+h+26}}
  if(side==='right'){const ky=sy-h/2-8;return{kx:sx+36,ky,cx:sx+88,cy:sy+h/2+96,lx:sx+36+w/2,ly:ky-32}}
  const ky=sy-h/2-8;return{kx:sx-36-w,ky,cx:sx-88,cy:sy+h/2+96,lx:sx-36-w/2,ly:ky-32};
}
function sceneSVG(th,variant,o){
  o=o||{};const g=GEO[variant],[W,H]=g.vb,u=o.uid||'x',p=th.p,mini=!!o.mini;
  let st='',ch='';
  STAGES.forEach(s=>{const [sx,sy,side]=g.st[s],pl=place(side,sx,sy);
    st+=kioskSVG(s,th,104,84,pl.ky,pl.kx);
    if(!mini)st+=`<text class="lab" x="${pl.lx}" y="${pl.ly}" text-anchor="middle" font-size="${variant==='portrait'?23:19}" data-lab="${s}" style="fill:#fff;stroke:rgba(0,0,0,.6);stroke-width:3.4px"></text>`;
    ch+=`<g transform="translate(${pl.cx} ${pl.cy}) scale(${variant==='portrait'?.95:.9})" data-role="${STAGE_ROLE[s]}">${charSVG(STAGE_ROLE[s],th)}</g>`;
    if(s==='report')ch+=`<g transform="translate(${pl.cx+(side==='bottom'?-52:50)} ${pl.cy}) scale(.82)" data-role="evolver">${charSVG('evolver',th)}</g>`;
  });
  const bin=g.bin;
  const binSVG=mini?'':`<g transform="translate(${bin[0]} ${bin[1]})"><path d="M-22 -26H22L17 22H-17Z" fill="#6b7280" stroke="${p.ink}" stroke-width="3"/><path d="M-26 -26H26" stroke="${p.ink}" stroke-width="5" stroke-linecap="round"/><path d="M-8 -12V12M0 -12V12M8 -12V12" stroke="#d1d5db" stroke-width="2.4"/><text class="lab" x="0" y="48" text-anchor="middle" font-size="20" data-lab="bin" style="fill:#fff;stroke:rgba(0,0,0,.6);stroke-width:3.4px"></text></g>`;
  const miniChars=mini?`<g transform="translate(300 430) scale(1.6)">${charSVG('brander',th)}</g><g transform="translate(640 430) scale(1.6)">${charSVG('gatekeeper',th)}</g><g transform="translate(980 430) scale(1.6)">${charSVG('poster',th)}</g>`:'';
  const miniBelt=mini?`<path d="M0 440H1280" stroke="${p.ink}" stroke-width="48"/><path d="M0 440H1280" stroke="${p.belt}" stroke-width="40"/><path d="M0 440H1280" stroke="${p.line}" stroke-width="3" stroke-dasharray="2 16"/>`:'';
  const inner=mini
   ?`${th.decor(W,H,u)}${miniBelt}${miniChars}`
   :`${th.decor(W,H,u)}
     <path d="${g.path}" fill="none" stroke="${p.ink}" stroke-width="48" stroke-linejoin="round"/>
     <path id="beltPath" d="${g.path}" fill="none" stroke="${p.belt}" stroke-width="40"/>
     <path d="${g.path}" fill="none" stroke="${p.line}" stroke-width="3" stroke-dasharray="2 16" class="beltflow"/>
     ${st}${ch}${binSVG}<g id="barriers"></g><g id="items"></g>`;
  return `<svg class="scene" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Factory scene">${inner}</svg>`;
}
