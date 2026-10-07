/* ===== 3D factory (Three.js, procedural low-poly, theme-driven).
   Seven houses stand on a wide ring, one per stage, each a cutaway with no front wall, so the camera in front of a house sees
   its rooms like a flat facade while everything is real 3D. A round belt runs in front of the houses. They are far apart:
   from one house you cannot see another. A second camera looks at the whole world from above, view only. ===== */
const K3=1.78,AG=1.25,PX3=28;   // decor scale, agent scale, belt pixels per world unit
const RING={Rb:52,Rf:58.5,BW:3.0,A0:Math.PI-.3,ITS:2.8};   // belt radius, house-front radius, belt width, path start angle, item scale
const PATH3={L:2*Math.PI*RING.Rb};
function pt3(s){const L=PATH3.L;s=((s%L)+L)%L;const a=RING.A0+s/RING.Rb;return{x:RING.Rb*Math.cos(a),z:RING.Rb*Math.sin(a),dx:-Math.sin(a),dz:Math.cos(a),a}}
const stAng=k=>Math.PI+STAGES.indexOf(k)*2*Math.PI/7;
const ST3={};STAGES.forEach(k=>{ST3[k]={s:(stAng(k)-RING.A0)*RING.Rb}});
const GATE_AT={review:3.88,publish:4.88};   // where items wait, in canonical progress
function geo3(){const a=[0];STAGES.forEach(k=>a.push(ST3[k].s/PATH3.L));a.push(1);SIM.anchors['3d']=a;SIM.len['3d']=PATH3.L*PX3}
const cToS=c=>{const a=SIM.anchors['3d'],i=Math.min(7,Math.floor(c));return(a[i]+(a[i+1]-a[i])*(c-i))*PATH3.L};
const lerp=(a,b,t)=>a+(b-a)*t;
const clampN=(v,a,b)=>Math.max(a,Math.min(b,v));

const webglOK=()=>{try{const c=document.createElement('canvas');return !!(window.WebGLRenderingContext&&(c.getContext('webgl2')||c.getContext('webgl')))}catch(e){return false}};
const THREE_OK=()=>typeof THREE!=='undefined'&&webglOK();

/* ---- tiny builders ---- */
const LM=(c,o)=>new THREE.MeshLambertMaterial(Object.assign({color:c,flatShading:true},o||{}));
const MB=c=>new THREE.MeshBasicMaterial({color:c});
const at=(m,x,y,z)=>{m.position.set(x||0,y||0,z||0);return m};
const bx=(w,h,d,c,x,y,z)=>at(new THREE.Mesh(new THREE.BoxGeometry(w,h,d),LM(c)),x,y,z);
const cy=(rt,rb,h,c,x,y,z,sg)=>at(new THREE.Mesh(new THREE.CylinderGeometry(rt,rb,h,sg||10),LM(c)),x,y,z);
const sp=(r,c,x,y,z,sg)=>at(new THREE.Mesh(new THREE.SphereGeometry(r,sg||10,sg?Math.max(6,sg-2):8),LM(c)),x,y,z);
const cn=(r,h,c,x,y,z,sg)=>at(new THREE.Mesh(new THREE.ConeGeometry(r,h,sg||8),LM(c)),x,y,z);
const hull=(m,ink,k)=>{const o=new THREE.Mesh(m.geometry,new THREE.MeshBasicMaterial({color:ink,side:THREE.BackSide}));o.scale.setScalar(1+((k||1.06)-1)*.55);m.add(o);return m};
const ctex=(w,h,fn)=>{const c=document.createElement('canvas');c.width=w;c.height=h;fn(c.getContext('2d'),w,h);const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=4;return t};
function svgTex(svg,w,h){const c=document.createElement('canvas');c.width=w;c.height=h;const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;const im=new Image();im.onload=()=>{c.getContext('2d').drawImage(im,0,0,w,h);t.needsUpdate=true};im.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);return t}
function rasterTex(src,w,h){const c=document.createElement('canvas');c.width=w;c.height=h;const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;const im=new Image();im.onload=()=>{c.getContext('2d').drawImage(im,0,0,w,h);t.needsUpdate=true};im.src=src;return t}
function labelTex(text,size){return ctex(512,96,(g,w,h)=>{g.font=`800 ${size||50}px "Bricolage Grotesque","Avenir Next",system-ui,sans-serif`;g.textAlign='center';g.textBaseline='middle';g.lineJoin='round';g.lineWidth=11;g.strokeStyle='rgba(8,20,14,.85)';g.strokeText(text,w/2,h/2+3);g.fillStyle='#fff';g.fillText(text,w/2,h/2+3)})}
const sprite=(tex,sx,sy,x,y,z)=>{const s=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false}));s.scale.set(sx,sy,1);s.position.set(x||0,y||0,z||0);return s};
const gradTex=(top,bot)=>ctex(8,256,(g,w,h)=>{const gr=g.createLinearGradient(0,0,0,h);gr.addColorStop(0,top);gr.addColorStop(1,bot);g.fillStyle=gr;g.fillRect(0,0,w,h)});
const mixHex=(a,b,k)=>'#'+new THREE.Color(a).lerp(new THREE.Color(b),k).getHexString();
const blob=(r,o)=>{const m=new THREE.Mesh(new THREE.CircleGeometry(r,18),new THREE.MeshBasicMaterial({color:0x000000,transparent:true,opacity:o||.22,depthWrite:false}));m.rotation.x=-Math.PI/2;m.position.y=.02;return m};

/* ---- theme extras for 3D (ground, plaza pattern, decor) ---- */
const TH3={
 br:{ground:'#58b977',plaza:(g,w,h)=>{g.fillStyle='#f7fbff';g.fillRect(0,0,w,h);g.fillStyle='#7ea3ec';[[.25,.5],[.75,.5],[.5,.25],[.5,.75]].forEach(([x,y])=>{g.beginPath();g.arc(x*w,y*h,w*.2,0,7);g.fill()});g.fillStyle='#f7fbff';g.beginPath();g.arc(w/2,h/2,w*.13,0,7);g.fill();g.fillStyle='#ffd23f';g.beginPath();g.arc(w/2,h/2,w*.05,0,7);g.fill();g.strokeStyle='#c9d8f5';g.lineWidth=3;g.strokeRect(0,0,w,h)},
  decor(G,th,an){const trunk='#8a5a2b';
   const palm=(x,z,s)=>{const g=new THREE.Group();const t=cy(.14*s,.2*s,3*s,trunk,0,1.5*s,0,7);t.rotation.z=.12;g.add(t);for(let i=0;i<7;i++){const l=sp(1,'#1b8a45',0,3.1*s,0,6);l.scale.set(1.5*s,.14*s,.45*s);l.rotation.y=i*0.9;l.position.set(Math.cos(i*.9)*.9*s+.2,3.05*s-.08*i%0.3,Math.sin(i*.9)*.9*s);l.rotation.z=.22;g.add(l)}g.position.set(x,0,z);G.add(g);an.push(t=>{g.rotation.z=Math.sin(t*.8+x)*.015})};
   [[-13,-8,1.1],[13,-9,1],[-14,6,1.2],[14,7,1.05],[-9,-11,.9],[10,-12,1]].forEach(a=>palm(...a));
   const pole=(x,z)=>G.add(cy(.07,.08,4.4,'#6b4a2a',x,2.2,z,6));pole(-11,-8.6);pole(11,-8.6);
   const cs=['#ffd23f','#25a050','#2a62c9','#ffffff'];const flags=[];for(let i=0;i<=16;i++){const t=i/16,x=-11+22*t,y=4.2-Math.sin(t*Math.PI)*.0-(.9*Math.sin(t*Math.PI)),f=at(new THREE.Mesh(new THREE.ConeGeometry(.2,.42,3),LM(cs[i%4])),x,y-.2,-8.6);f.rotation.x=Math.PI;f.rotation.y=.5;G.add(f);flags.push(f)}
   an.push(t=>flags.forEach((f,i)=>{f.rotation.z=Math.sin(t*2+i)*.12}));
   const sun=new THREE.Mesh(new THREE.SphereGeometry(2.2,16,12),MB('#ffe27a'));sun.position.set(-15,10,-19);G.add(sun)}},
 cn:{ground:'#5a0b14',plaza:(g,w,h)=>{g.fillStyle='#470a10';g.fillRect(0,0,w,h);g.strokeStyle='#f5c542';g.lineWidth=6;g.beginPath();g.moveTo(w/2,w*.1);g.lineTo(w*.9,h/2);g.lineTo(w/2,h*.9);g.lineTo(w*.1,h/2);g.closePath();g.stroke();g.fillStyle='#f5c542';g.beginPath();g.arc(w/2,h/2,w*.05,0,7);g.fill()},
  decor(G,th,an){const lant=[];const lp=(x,z)=>{const g=new THREE.Group();g.add(cy(.07,.08,4.2,'#f5c542',0,2.1,0,6));const l=sp(.5,'#e0212f',0,3.6,0,10);l.scale.y=1.15;g.add(l,cy(.22,.22,.1,'#f5c542',0,4.18,0),cy(.22,.22,.1,'#f5c542',0,3.0,0));g.add(at(new THREE.Mesh(new THREE.CylinderGeometry(.015,.015,.6,4),MB('#f5c542')),0,2.7,0));g.position.set(x,0,z);G.add(g);lant.push(g)};
   [[-12,-8],[-6,-9],[0,-9.5],[6,-9],[12,-8],[-12,6],[12,6],[-14,0],[14,0]].forEach(a=>lp(...a));an.push(t=>lant.forEach((g,i)=>{g.rotation.z=Math.sin(t*1.3+i)*.04}));
   const gate=new THREE.Group();gate.add(cy(.28,.3,4.2,'#c8102e',-2.6,2.1,0,10),cy(.28,.3,4.2,'#c8102e',2.6,2.1,0,10),bx(6.6,.5,.7,'#c8102e',0,4.2,0),bx(7.4,.22,1,'#f5c542',0,4.6,0));gate.position.set(-9-3.2,0,0);gate.rotation.y=Math.PI/2;gate.scale.setScalar(.85);G.add(gate);
   const moon=new THREE.Mesh(new THREE.SphereGeometry(2.4,16,12),MB('#f5c542'));moon.position.set(14,10,-18);G.add(moon)}},
 us:{ground:'#bfe3b0',plaza:(g,w,h)=>{g.fillStyle='#fff';g.fillRect(0,0,w,h);g.fillStyle='#1b2a5c';g.fillRect(0,0,w/2,h/2);g.fillRect(w/2,h/2,w/2,h/2)},
  decor(G,th,an){const lamp=(x,z)=>{G.add(cy(.06,.08,3.6,'#444',x,1.8,z,6),sp(.32,'#fff6c8',x,3.7,z,8))};[[-12,-8],[12,-8],[-12,6],[12,6]].forEach(a=>lamp(...a));
   const sign=new THREE.Mesh(new THREE.PlaneGeometry(4.6,1.8),new THREE.MeshBasicMaterial({map:ctex(256,100,(g,w,h)=>{g.fillStyle='#1b2a5c';g.fillRect(0,0,w,h);g.strokeStyle='#ff4d6d';g.lineWidth=8;g.strokeRect(6,6,w-12,h-12);g.font='800 54px sans-serif';g.textAlign='center';g.textBaseline='middle';g.fillStyle='#ff8aa1';g.fillText('OPEN',w/2,h/2+3)})}));sign.position.set(0,6.2,-12.5);G.add(sign);
   const cl=[];for(let i=0;i<4;i++){const g=new THREE.Group();g.add(sp(1.2,'#fff',0,0,0,8),sp(1.0,'#fff',1.2,-.2,0,8),sp(.9,'#fff',-1.1,-.2,0,8));g.position.set(-16+i*11,10+((i*3)%3),-16);G.add(g);cl.push(g)}an.push(t=>cl.forEach((g,i)=>{g.position.x+=Math.sin(t*.2+i)*.004}));
   const aw=bx(30,.35,.7,'#d92d2d',0,6.2,-9.4);G.add(aw)}},
 ru:{ground:'#e9eef8',plaza:(g,w,h)=>{g.fillStyle='#1a1328';g.fillRect(0,0,w,h);g.fillStyle='#c62d3a';g.beginPath();g.arc(w/2,h/2,w*.17,0,7);g.fill();g.fillStyle='#d9a441';[[.5,.2],[.5,.8],[.2,.5],[.8,.5]].forEach(([x,y])=>{g.beginPath();g.arc(x*w,y*h,w*.09,0,7);g.fill()});g.strokeStyle='#5aa85a';g.lineWidth=5;g.beginPath();g.moveTo(0,h/2);g.quadraticCurveTo(w*.25,h*.3,w*.5,h/2);g.quadraticCurveTo(w*.75,h*.7,w,h/2);g.stroke()},
  decor(G,th,an){const dome=(x,z,s,c)=>{const g=new THREE.Group();g.add(cy(.9*s,.9*s,3.2*s,'#e9d9bd',0,1.6*s,0,12));const d=sp(1.15*s,c,0,3.9*s,0,12);d.scale.y=1.35;g.add(d,cn(.2*s,1*s,'#d9a441',0,5.4*s,0,8));g.position.set(x,0,z);G.add(g)};
   dome(-10,-15,.8,'#c62d3a');dome(0,-17,1.05,'#2a62c9');dome(10,-15,.75,'#d9a441');
   const N=140,pos=new Float32Array(N*3);for(let i=0;i<N;i++){pos[i*3]=(Math.random()-.5)*34;pos[i*3+1]=Math.random()*12;pos[i*3+2]=(Math.random()-.5)*26}
   const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.BufferAttribute(pos,3));const snow=new THREE.Points(geo,new THREE.PointsMaterial({color:0xffffff,size:.16,transparent:true,opacity:.9}));G.add(snow);
   an.push((t,dt)=>{const p=geo.attributes.position;for(let i=0;i<N;i++){let y=p.getY(i)-dt*.8;if(y<0)y=12;p.setY(i,y);p.setX(i,p.getX(i)+Math.sin(t+i)*.002)}p.needsUpdate=true})}},
 jp:{ground:'#f7c8d8',plaza:(g,w,h)=>{g.fillStyle='#21377a';g.fillRect(0,0,w,h);g.strokeStyle='#9fb4ee';g.lineWidth=4;for(let r=14;r<w*.62;r+=14){g.beginPath();g.arc(w/2,h*.9,r,Math.PI,0);g.stroke();g.beginPath();g.arc(0,h*.4,r,Math.PI*1.5,Math.PI*.5,false);g.stroke()}},
  decor(G,th,an){const tree=(x,z,s)=>{G.add(cy(.18*s,.26*s,2.6*s,'#6b4a3a',x,1.3*s,z,7));[[0,3.2,0,1.5],[1,2.8,.4,1.1],[-1,2.9,-.3,1.2],[.2,3.9,.2,1]].forEach(([dx,dy,dz,r])=>G.add(sp(r*s,'#ffb3c8',x+dx*s,dy*s,z+dz*s,8)))};tree(-12,-8,1.1);tree(12,-9,1);tree(-13,6,1.2);tree(13,7,1);tree(-8,-12,1);
   const torii=new THREE.Group();torii.add(cy(.25,.3,4,'#cf3d4f',-2.2,2,0,10),cy(.25,.3,4,'#cf3d4f',2.2,2,0,10),bx(6.2,.45,.6,'#cf3d4f',0,4.1,0),bx(5.2,.3,.5,'#2a2a4a',0,3.4,0));torii.position.set(9+3.8,0,0);torii.rotation.y=Math.PI/2;torii.scale.setScalar(.85);G.add(torii);
   const sun=new THREE.Mesh(new THREE.CircleGeometry(2.6,24),MB('#d6283f'));sun.position.set(13,9,-18);G.add(sun);
   const N=90,pos=new Float32Array(N*3);for(let i=0;i<N;i++){pos[i*3]=(Math.random()-.5)*34;pos[i*3+1]=Math.random()*9;pos[i*3+2]=(Math.random()-.5)*26}
   const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.BufferAttribute(pos,3));G.add(new THREE.Points(geo,new THREE.PointsMaterial({color:0xff9ab7,size:.22,transparent:true,opacity:.95})));
   an.push((t,dt)=>{const p=geo.attributes.position;for(let i=0;i<N;i++){let y=p.getY(i)-dt*.55;if(y<0)y=9;p.setY(i,y);p.setX(i,p.getX(i)+Math.sin(t*.8+i)*.006)}p.needsUpdate=true})}},
 dragons:{ground:'#241347',plaza:(g,w,h)=>{g.fillStyle='#2b2140';g.fillRect(0,0,w,h);g.strokeStyle='#ff8a3d';g.lineWidth=4;for(let i=0;i<4;i++){g.beginPath();g.arc(w/2,h*(.15+i*.25),w*.2,0,Math.PI);g.stroke()}},
  decor(G,th,an){[[-14,-12,3.4,6],[-8,-14,2.6,5],[0,-16,4,8],[8,-14,2.8,5.5],[15,-12,3.4,6.5],[-17,2,3,5],[17,3,3,5.5]].forEach(([x,z,r,h])=>G.add(cn(r,h,'#1d0f3e',x,h/2,z,5)));
   const moon=new THREE.Mesh(new THREE.SphereGeometry(1.8,16,12),MB('#ffe8b8'));moon.position.set(-14,10,-18);G.add(moon);
   const d=new THREE.Group();const dk='#14082c';d.add(at(new THREE.Mesh(new THREE.SphereGeometry(.7,8,6),LM(dk)),0,0,0));d.children[0].scale.set(2.6,.6,.7);const wing=()=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(new Float32Array([0,0,0, -.4,0,2.8, 1.4,0,1.2, 0,0,0, 1.4,0,1.2, 1.9,0,-.3]),3));g.computeVertexNormals();return new THREE.Mesh(g,new THREE.MeshBasicMaterial({color:dk,side:THREE.DoubleSide}))};
   const w1=wing(),w2=wing();w2.scale.z=-1;d.add(w1,w2,at(new THREE.Mesh(new THREE.ConeGeometry(.28,1.8,5),LM(dk)),-2.1,0,0),at(new THREE.Mesh(new THREE.SphereGeometry(.38,8,6),LM(dk)),1.9,.1,0));d.children[d.children.length-2].rotation.z=Math.PI/2;d.scale.setScalar(1.6);G.add(d);
   an.push(t=>{const a=t*.25;d.position.set(Math.cos(a)*13,8.5+Math.sin(t*.7)*.6,Math.sin(a)*9-3);d.rotation.y=-a+Math.PI;w1.rotation.x=Math.sin(t*5)*.5;w2.rotation.x=-Math.sin(t*5)*.5});
   const N=70,pos=new Float32Array(N*3);for(let i=0;i<N;i++){pos[i*3]=(Math.random()-.5)*34;pos[i*3+1]=Math.random()*9;pos[i*3+2]=(Math.random()-.5)*26}const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.BufferAttribute(pos,3));G.add(new THREE.Points(geo,new THREE.PointsMaterial({color:0xffb347,size:.18,transparent:true,opacity:.9})));
   an.push((t,dt)=>{const p=geo.attributes.position;for(let i=0;i<N;i++){let y=p.getY(i)+dt*.7;if(y>9)y=0;p.setY(i,y)}p.needsUpdate=true})}},
 realms:{ground:'#6f7064',plaza:(g,w,h)=>{g.fillStyle='#7c7d72';g.fillRect(0,0,w,h);g.strokeStyle='#55564c';g.lineWidth=4;for(let y=0;y<h;y+=h/4){g.beginPath();g.moveTo(0,y);g.lineTo(w,y);g.stroke();for(let x=((y/(h/4))%2)*w/4;x<w;x+=w/2){g.beginPath();g.moveTo(x,y);g.lineTo(x,y+h/4);g.stroke()}}},
  decor(G,th,an){const castle=new THREE.Group();castle.add(bx(7,4,3,'#6a6d78',0,2,0),cy(1.1,1.1,6,'#6a6d78',-4.2,3,0,12),cy(1.1,1.1,6,'#6a6d78',4.2,3,0,12),cn(1.5,2.2,'#8a1f2b',-4.2,7.1,0,12),cn(1.5,2.2,'#8a1f2b',4.2,7.1,0,12),bx(2.2,6.4,2.2,'#6a6d78',0,3.2,-.8),cn(1.7,2,'#8a1f2b',0,7.4,-.8,4));for(let i=-3;i<=3;i++)castle.add(bx(.55,.6,3.2,'#6a6d78',i*1.05,4.3,0));castle.position.set(0,0,-15);G.add(castle);
   const hill=sp(9,'#6d7a62',0,-6.5,-15,12);hill.scale.set(1.6,.8,1);G.add(hill);
   const banners=[];[[-12,-7,'#8a1f2b'],[-6,-9,'#2d4a8a'],[6,-9,'#c9a227'],[12,-7,'#8a1f2b'],[-12,6,'#2d4a8a'],[12,6,'#c9a227']].forEach(([x,z,c])=>{G.add(cy(.06,.07,4.4,'#444',x,2.2,z,6));const b=new THREE.Mesh(new THREE.PlaneGeometry(.9,1.8),new THREE.MeshBasicMaterial({color:c,side:THREE.DoubleSide}));b.position.set(x+.5,3.4,z);G.add(b);banners.push(b)});
   an.push(t=>banners.forEach((b,i)=>{b.rotation.y=Math.sin(t*2+i)*.25}));
   [[-10,-5],[10,-5],[-10,5],[10,5]].forEach(([x,z])=>{G.add(cy(.06,.07,1.6,'#3a2a1a',x,.8,z,6),cn(.22,.6,'#ff9a2a',x,1.9,z,6));G.children[G.children.length-1].material=MB('#ff9a2a')})}},
 courtyard:{ground:'#c5724b',plaza:(g,w,h)=>{g.fillStyle='#d6845a';g.fillRect(0,0,w,h);g.fillStyle='#c5724b';for(let y=0;y<4;y++)for(let x=0;x<2;x++){g.fillRect(x*w/2+((y%2)*w/4),y*h/4+4,w/2-8,h/4-8)}},
  decor(G,th,an){const wall=bx(34,7,.8,'#d9a56e',0,3.5,-13);G.add(wall);[['#2f6fda',-9],['#2f9a5a',0],['#e85d2a',9]].forEach(([c,x])=>{G.add(bx(2.2,4.2,.3,c,x,2.1,-12.5),bx(1.4,1.4,.25,'#fff6dd',x,5.2,-12.5))});
   const cl=[];const cols=['#2f6fda','#fff','#e85d2a','#f5c542','#2f9a5a'];G.add(at(new THREE.Mesh(new THREE.CylinderGeometry(.02,.02,26,4),MB('#3a1f12')),0,5.6,-9));G.children[G.children.length-1].rotation.z=Math.PI/2;
   for(let i=0;i<9;i++){const c=new THREE.Mesh(new THREE.PlaneGeometry(1,1.3),new THREE.MeshBasicMaterial({color:cols[i%5],side:THREE.DoubleSide}));c.position.set(-11+i*2.75,5,-9);G.add(c);cl.push(c)}an.push(t=>cl.forEach((c,i)=>{c.rotation.y=Math.sin(t*1.6+i)*.3}));
   G.add(cy(.8,.8,1.2,'#a9703f',-12,.6,-7,12),cy(.8,.8,.15,'#c58a52',-12,1.25,-7,12),cy(.45,.35,.7,'#b8472a',12,.35,-7,8),cn(.5,.9,'#2f9a5a',12,1.15,-7,6))}},
 tiny:{ground:'#bfe8d8',plaza:(g,w,h)=>{g.fillStyle='#fff';g.fillRect(0,0,w,h);g.fillStyle='#ffd6e0';g.beginPath();g.arc(w*.25,h*.25,w*.12,0,7);g.fill();g.fillStyle='#cdeee1';g.beginPath();g.arc(w*.75,h*.75,w*.12,0,7);g.fill();g.fillStyle='#ffe3b8';g.beginPath();g.arc(w*.75,h*.25,w*.07,0,7);g.fill();g.beginPath();g.arc(w*.25,h*.75,w*.07,0,7);g.fill()},
  decor(G,th,an){const gears=[];const gear=(x,y,z,r,c)=>{const g=new THREE.Group();g.add(cy(r,r,.35,c,0,0,0,18));for(let i=0;i<10;i++){const t=bx(r*.3,.35,r*.34,c,0,0,0);const a=i*Math.PI/5;t.position.set(Math.cos(a)*r*1.12,0,Math.sin(a)*r*1.12);t.rotation.y=-a;g.add(t)}g.add(cy(r*.4,r*.4,.4,'#fff',0,0,0,12));g.rotation.x=Math.PI/2;g.position.set(x,y,z);G.add(g);gears.push(g)};
   gear(-13,3,-8,1.4,'#ffb86b');gear(-10.4,2.2,-8,.9,'#ff9bb3');gear(14,2.5,-7,1.2,'#7fd6c1');gear(12.2,3.4,-9,.8,'#ffb86b');
   an.push((t)=>gears.forEach((g,i)=>{g.rotation.y=t*(i%2?-.6:.6)}));
   const cl=[];for(let i=0;i<5;i++){const g=new THREE.Group();g.add(sp(1.3,'#fff',0,0,0,8),sp(1.05,'#fff',1.3,-.2,0,8),sp(.95,'#fff',-1.2,-.2,0,8));g.position.set(-18+i*9,9.5+(i%2)*1.2,-14);G.add(g);cl.push(g)}an.push(t=>cl.forEach((g,i)=>{g.position.x+=Math.sin(t*.3+i)*.005}));
   [['#ffb3c8',6.4],['#ffe0a3',6.0],['#bfe8d8',5.6]].forEach(([c,r],i)=>{const tor=new THREE.Mesh(new THREE.TorusGeometry(r,.22,6,28,Math.PI),new THREE.MeshBasicMaterial({color:c}));tor.position.set(0,0,-14);G.add(tor)})}}
};

/* ---- agents (3D low-poly robots, or 2D sprites standing in the 3D world) ---- */
function agent3(role,th,style){
  const p=th.p,ink=p.ink,g=new THREE.Group(),A={g,role,mode:'home',t:0,ph:Math.random()*6,face:0,workDur:1.1,style,limbs:{}};
  g.add(blob(.5));{const hit=new THREE.Mesh(new THREE.SphereGeometry(.85,8,6),new THREE.MeshBasicMaterial({visible:false}));hit.position.y=1.0;g.add(hit);g.userData.role=role}
  if(style==='sprite'){
    const art=th.id==='br'&&ART.chars[role];
    if(art){const hh=2.5,s=sprite(rasterTex(art.src,art.w,art.h),hh*art.w/art.h,hh,0,hh/2+.04,0);g.add(s);A.sprite=s;A.sy=hh/2+.04;return A}
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="220" height="300" viewBox="-46 -122 92 128">${charSVG(role,th)}</svg>`;
    const s=sprite(svgTex(svg,220,300),1.7,2.3,0,1.2,0);g.add(s);A.sprite=s;A.sy=1.2;return A}
  const bodyC=p.body,dark=shade(bodyC,-.25),legG=new THREE.CylinderGeometry(.1,.1,.36,8);legG.translate(0,-.18,0);
  const legL=at(new THREE.Mesh(legG,LM(dark)),-.15,.38,0),legR=at(new THREE.Mesh(legG,LM(dark)),.15,.38,0);
  const torso=hull(bx(.58,.56,.4,bodyC,0,.66,0),ink,1.07);
  const armG=new THREE.CylinderGeometry(.085,.085,.44,8);armG.translate(0,-.22,0);
  const armL=at(new THREE.Mesh(armG,LM(bodyC)),-.38,.9,0),armR=at(new THREE.Mesh(armG,LM(bodyC)),.38,.9,0);
  const head=hull(bx(.66,.6,.6,p.head,0,1.28,0),ink,1.06);
  const eye=new THREE.SphereGeometry(.065,8,6);
  const body=new THREE.Group();body.add(torso,head,armL,armR,at(new THREE.Mesh(eye,MB(ink)),-.16,1.32,.31),at(new THREE.Mesh(eye,MB(ink)),.16,1.32,.31),at(new THREE.Mesh(new THREE.CircleGeometry(.11,10),new THREE.MeshBasicMaterial({color:p.accent})),0,.7,.205));
  const mouth=at(new THREE.Mesh(new THREE.TorusGeometry(.09,.015,4,8,Math.PI),MB(ink)),0,1.16,.31);mouth.rotation.z=Math.PI;body.add(mouth);
  const hand=(m,x)=>{m.position.set(x,-.44,.02);armR.add(m)};
  const ant=()=>{body.add(cy(.02,.02,.24,ink,0,1.7,0,5),sp(.065,p.accent,0,1.84,0,8))};
  if(role==='brander'){ant();const br=cy(.025,.025,.6,ink,0,-.06,0,6);br.rotation.x=1.2;hand(br,0);br.add(cn(.07,.18,p.accent,0,.36,0,6));armL.add(cy(.17,.17,.03,p.accent,0,-.46,.02,12))}
  else if(role==='ideator'){body.add(cy(.05,.05,.12,ink,0,1.64,0,6));const bulb=sp(.2,'#ffe27a',0,1.9,0,10);bulb.material=MB('#ffe27a');body.add(bulb);A.bulb=bulb}
  else if(role==='director'){ant();const c=new THREE.Group();c.add(bx(.42,.26,.06,ink,0,0,0),bx(.42,.1,.07,'#fff',0,.17,0));for(let i=-1;i<=1;i++)c.add(bx(.06,.1,.08,ink,i*.14,.17,0));c.rotation.z=.2;hand(c,0);c.position.set(0,-.48,.12)}
  else if(role==='gatekeeper'){const hat=new THREE.Mesh(new THREE.SphereGeometry(.4,12,6,0,Math.PI*2,0,Math.PI/2),LM('#ffd23f'));hat.position.set(0,1.54,0);body.add(hat,cy(.46,.46,.05,'#ffd23f',0,1.55,0,14));const pole=cy(.03,.03,1.3,ink,.62,.65,.12,6),disc=cy(.2,.2,.05,p.gate,.62,1.36,.12,10);disc.rotation.x=Math.PI/2;g.add(pole,disc);A.paddle=[pole,disc]}
  else if(role==='poster'){ant();const m=new THREE.Group();const cone=cn(.2,.46,p.accent,0,.0,.2,10);cone.rotation.x=Math.PI/2;m.add(cone,cy(.06,.06,.2,ink,0,0,-.12,6));m.rotation.x=-.3;hand(m,0);m.position.set(0,-.46,.12)}
  else if(role==='analyst'){ant();const m=new THREE.Group();const ring=new THREE.Mesh(new THREE.TorusGeometry(.15,.028,6,14),LM(ink));ring.position.set(0,.05,0);const gl=new THREE.Mesh(new THREE.CircleGeometry(.14,12),new THREE.MeshBasicMaterial({color:0xcfeaff,transparent:true,opacity:.6}));gl.position.set(0,.05,0);m.add(ring,gl,cy(.02,.02,.26,ink,.09,-.14,0,5));m.children[2].rotation.z=-.7;hand(m,0);m.position.set(0,-.46,.14);[-.1,0,.1].forEach((x,i)=>body.add(bx(.06,.1+i*.05,.02,'#fff',x,.58+i*.025,.21)))}
  else if(role==='reflector'){ant();const m=new THREE.Group();const d=cy(.18,.18,.03,'#cfeaff',0,0,0,14);d.rotation.x=Math.PI/2;const rim=new THREE.Mesh(new THREE.TorusGeometry(.18,.02,6,16),LM(ink));m.add(d,rim,cy(.025,.025,.22,ink,0,-.2,0,5));hand(m,0);m.position.set(0,-.5,.12)}
  else{body.add(cy(.02,.02,.2,ink,0,1.68,0,5));[-1,1].forEach(s=>{const l=sp(.16,s<0?'#5cc66b':'#7fd98a',s*.14,1.82,0,8);l.scale.set(1.3,.5,.7);l.rotation.z=s*.5;body.add(l)})}
  g.add(legL,legR,body);Object.assign(A.limbs,{legL,legR,armL,armR,body});return A}


/* ---- the scene ---- */
const SceneThree={host:null,hidden:false,variant:'3d',charPos:{},R:null,scn:null,cam:null,canvas:null,ro:null,items:new Map(),agents:{},bubs:[],anims:[],tex:{},bars_:{},
 cv:{hz:1,haz:0,hpol:0,hd:null,wz:1,waz:0,wpol:1.12,wpx:0,wpz:0,fa:null,lat:0,wm:0,idle:0,tw:{}},
 safe:{l:0,t:0,r:0,b:0},fx:{track:null,sel:null,need:{}},bin:null,clock:0,kiosks:[],kw:1,kh:1,Dw:200,
 mount(h){if(!THREE_OK())return;this.host=h;h.dataset.mode='3d';GATES.review.at=GATE_AT.review;GATES.publish.at=GATE_AT.publish;const slot=$('.slot',h);this.canvas=document.createElement('canvas');this.canvas.className='three';slot.appendChild(this.canvas);
  this.R=new THREE.WebGLRenderer({canvas:this.canvas,antialias:!Q.get('lowfx'),alpha:false,powerPreference:'high-performance'});this.R.setPixelRatio(Math.min(window.devicePixelRatio||1,2));this.R.shadowMap.enabled=true;this.R.shadowMap.type=THREE.PCFSoftShadowMap;this.R.autoClear=false;
  this.cv.fa=null;this.cv.hd=null;this.cv.wm=S.world?1:0;this.build();this.size();this.ro=('ResizeObserver' in window)?new ResizeObserver(()=>this.size()):null;if(this.ro)this.ro.observe(slot);this.bindPointer()},
 unmount(){if(typeof Snd!=='undefined')Snd.pause();if(this.keyH){window.removeEventListener('keydown',this.keyH);this.keyH=null}if(this.ro)this.ro.disconnect();this.ro=null;if(this.scn){this.scn.traverse(o=>{if(o.geometry)o.geometry.dispose();const m=o.material;if(m){(Array.isArray(m)?m:[m]).forEach(x=>{if(x.map)x.map.dispose();x.dispose()})}})}
  if(this.bgTex){this.bgTex.dispose();this.bgTex=null}if(this.R){this.R.dispose();this.R.forceContextLoss&&this.R.forceContextLoss()}this.R=null;this.scn=null;this.items.clear();this.agents={};this.bubs.forEach(b=>b.el.remove());this.bubs=[];this.anims=[];this.host=null;this.kiosks=[];this.canvas=null},
 build(){const th=TCUR(),p=th.p,ex=TH3[th.id],style=S.view==='3d-sprites'?'sprite':'model';
  this.anims=[];this.items.clear();this.agents={};this.kiosks=[];this.glow=[];this.halos=[];this.rings={};this.posters={};this.th=th;this.ex=ex;this.dark=['ru','dragons'].includes(th.id);this.lastFocus=null;this.nightLights=[];this.acts=[];this.glow2=[];this.adObjs=[];this.ptr={x:0,y:0};
  const sc=this.scn=new THREE.Scene();sc.fog=new THREE.Fog(p.sky2,40,120);
  // a flat back layer drawn first: the sky gradient and the painted scenery of the house in front
  this.bgScn=new THREE.Scene();this.bgCam=new THREE.OrthographicCamera(-1,1,1,-1,0,10);this.skyQ=new THREE.Mesh(new THREE.PlaneGeometry(2,2),new THREE.MeshBasicMaterial({depthTest:false,depthWrite:false}));this.skyQ.position.z=-5;this.bgScn.add(this.skyQ);
  this.hemi=new THREE.HemisphereLight('#ffffff',p.ground||ex.ground,2.0);
  const sun=this.sun=new THREE.DirectionalLight('#ffffff',2.4);sun.position.set(-16,30,16);sun.target.position.set(0,0,0);sun.castShadow=true;
  const shd=sun.shadow;shd.mapSize.set(Q.get('lowfx')?1024:2560,Q.get('lowfx')?1024:2560);Object.assign(shd.camera,{left:-26,right:26,top:26,bottom:-26,near:2,far:120});shd.bias=-.0004;shd.normalBias=.035;shd.radius=3;
  sc.add(this.hemi,sun,sun.target);
  const cam=this.cam=new THREE.PerspectiveCamera(36,16/9,.5,1500);
  const world=new THREE.Group();sc.add(world);this.world=world;this.fxInit(world);
  const flat=[];
  const ground=this.groundMesh=new THREE.Mesh(new THREE.CircleGeometry(700,48),LM(ex.ground));ground.rotation.x=-Math.PI/2;world.add(ground);flat.push(ground);
  // plaza: one big round courtyard under the houses and the belt
  const sh=new THREE.Shape();sh.absarc(0,0,RING.Rf+13,0,Math.PI*2,false);
  const pt=ctex(512,512,ex.plaza);pt.wrapS=pt.wrapT=THREE.RepeatWrapping;if(th.id==='br'&&ART.plaza){const im=new Image();im.onload=()=>{pt.image.getContext('2d').drawImage(im,0,0,512,512);pt.needsUpdate=true};im.src=ART.plaza}pt.repeat.set(1/6,1/6);const plaza=new THREE.Mesh(new THREE.ShapeGeometry(sh,72),new THREE.MeshLambertMaterial({map:pt}));plaza.rotation.x=-Math.PI/2;plaza.position.y=.01;world.add(plaza);flat.push(plaza);this.plazaM=plaza;
  // belt
  const N=this.N=Math.ceil(PATH3.L/.3),pos=[],uvB=[],uvT=[],idx=[],pos2=[],pos3=[];for(let i=0;i<=N;i++){const s=PATH3.L*i/N,q=pt3(s),nx=-q.dz,nz=q.dx,w=RING.BW/2;pos.push(q.x+nx*w,.12,q.z+nz*w,q.x-nx*w,.12,q.z-nz*w);pos2.push(q.x+nx*(w+.32),.06,q.z+nz*(w+.32),q.x-nx*(w+.32),.06,q.z-nz*(w+.32));pos3.push(q.x+nx*.42,.17,q.z+nz*.42,q.x-nx*.42,.17,q.z-nz*.42);uvB.push(s/1.6,0,s/1.6,1);uvT.push(s/2.2,0,s/2.2,1);if(i<N){const a=i*2;idx.push(a,a+1,a+2,a+1,a+3,a+2)}}
  const mk=(P,U,mat)=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(P,3));if(U)g.setAttribute('uv',new THREE.Float32BufferAttribute(U,2));g.setIndex(idx);g.computeVertexNormals();return new THREE.Mesh(g,mat)};
  world.add(mk(pos2,null,new THREE.MeshBasicMaterial({color:p.ink,side:THREE.DoubleSide})));
  const bt=this.beltTex=ctex(128,128,(g,w,h)=>{g.fillStyle=p.belt;g.fillRect(0,0,w,h);g.fillStyle=shade(p.belt,.18);for(let x=0;x<w;x+=w/4)g.fillRect(x,6,6,h-12);g.fillStyle=p.line;g.fillRect(0,5,w,3);g.fillRect(0,h-8,w,3)});bt.wrapS=THREE.RepeatWrapping;
  const belt=mk(pos,uvB,new THREE.MeshLambertMaterial({map:bt,side:THREE.DoubleSide}));world.add(belt);flat.push(belt);
  // the path the followed video already travelled (a flowing blue ribbon on the belt)
  const dt=this.dashTex=ctex(64,8,(g,w,h)=>{g.fillStyle='#2f8fe8';g.fillRect(0,0,w,h);g.fillStyle='#bfe3ff';g.fillRect(0,2,w*.5,h-4)});dt.wrapS=THREE.RepeatWrapping;dt.repeat.set(1,1);
  const trail=this.trail=mk(pos3,uvT,new THREE.MeshBasicMaterial({map:dt,transparent:true,opacity:.92,depthWrite:false,side:THREE.DoubleSide}));trail.geometry.setDrawRange(0,0);trail.renderOrder=2;world.add(trail);
  // houses: one per stage, on the ring, fronts looking at the middle
  this.pl={};this.labels={};this.icons={};
  const wm=this.winMat=new THREE.MeshLambertMaterial({color:'#dff1ff',emissive:'#ffcf7a',emissiveIntensity:0,flatShading:true});this.glow.push(wm);
  this.bldLamps={};this.roofLamps={};this.rugs={};
  STAGES.forEach(k=>{const a=stAng(k),ux=Math.cos(a),uz=Math.sin(a),Rc=RING.Rf+HD/2+.2;
    const P=this.pl[k]={a,ux,uz,kx:Rc*ux,kz:Rc*uz,ry:Math.atan2(-ux,-uz),q:pt3(ST3[k].s)};
    const B=this.makeHouse(k,p,wm,this.anims),g=B.g;Object.assign(P,{W:B.W,Ht:B.Ht,top:B.top,rooms:B.rooms,g});this.bldLamps[k]=B.lamps;this.roofLamps[k]=B.roofLamps;this.rugs[k]=B.rugs;
    g.position.set(P.kx,0,P.kz);g.rotation.y=P.ry;g.userData.stage=k;world.add(g);this.kiosks.push(g);
    if(th.id==='br'&&ART.scenes&&ART.scenes[k])P.scn=this.scenery(k,g,B.W,B.Ht,p);
    // pulse plate (selected / needs you), seen mostly from above
    const rg=new THREE.Group(),rm=new THREE.MeshBasicMaterial({color:SC[k],transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false}),dm=new THREE.MeshBasicMaterial({color:SC[k],transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false});
    const ringM=new THREE.Mesh(new THREE.PlaneGeometry(B.W+8,HD+8),rm),discM=new THREE.Mesh(new THREE.PlaneGeometry(B.W+5,HD+5),dm);ringM.rotation.x=discM.rotation.x=-Math.PI/2;ringM.position.y=.05;discM.position.y=.055;rg.add(ringM,discM);rg.position.set(P.kx,0,P.kz);rg.rotation.y=P.ry;world.add(rg);this.rings[k]={g:rg,rm,dm,v:0,k:1};P.rg=rg;
    const lab=sprite(labelTex(t('station.'+k)),8,1.5,P.kx,B.top+1.9,P.kz);lab.renderOrder=6;lab.material.depthTest=false;world.add(lab);this.labels[k]=lab;P.label=lab;
    const icon=ICON[k==='brand'?'brand':k==='ideas'?'ideas':k==='make'?'studio':k==='review'?'review':k==='publish'?'publish':k==='metrics'?'metrics':'report'];
    const itex=svgTex(`<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11.2" fill="#fff" stroke="${p.ink}" stroke-width="1.1"/><g fill="none" stroke="${p.ink}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" transform="translate(5 5) scale(.58)">${icon}</g></svg>`,128,128);
    const ic=sprite(itex,3,3,P.kx,B.top+4.6,P.kz);ic.visible=false;world.add(ic);this.icons[k]=ic;
    // the robot of this stage walks the rooms from side to side
    const floorY=.36,rz=1.3;P.rpos=B.rooms.map(r=>this.toWorld(k,r.x,floorY,rz));
    const ag=agent3(STAGE_ROLE[k],th,style);ag.k=k;ag.pat=P.rpos;ag.pi=0;ag.dir=1;ag.dw=0;ag.arrived=false;ag.home=P.rpos[0].clone();ag.work=null;ag.guard=null;ag.g.scale.setScalar(AG);ag.g.position.copy(P.rpos[0]);ag.g.rotation.y=P.ry;world.add(ag.g);this.agents[STAGE_ROLE[k]]=ag;
    if(k==='report'){const ev=agent3('evolver',th,style);ev.k=k;ev.pat=P.rpos.slice().reverse();ev.pi=0;ev.dir=1;ev.dw=1.5;ev.arrived=false;ev.home=ev.pat[0].clone();ev.work=null;ev.guard=null;ev.g.scale.setScalar(AG);ev.g.position.copy(ev.pat[0]);ev.g.rotation.y=P.ry;world.add(ev.g);this.agents.evolver=ev}});
  // painted scenery behind each house (generated art, Brazil theme): the world changes from house to house
  this.backs={};this.ROWS={brand:.64,ideas:.8,make:.6,review:.77,publish:.72,metrics:.72,report:.74};
  if(th.id==='br'&&ART.scenes)STAGES.forEach(k=>{if(!ART.scenes[k])return;const m=new THREE.MeshBasicMaterial({map:rasterTex(ART.scenes[k],1024,576),transparent:true,depthTest:false,depthWrite:false}),q=new THREE.Mesh(new THREE.PlaneGeometry(2,2),m);q.visible=false;q.position.z=-4;this.bgScn.add(q);this.backs[k]={q,m}});
  this.painted=Object.keys(this.backs).length>0;
  // a low curb where the paved courtyard ends and the scenery begins
  {const cb=new THREE.Mesh(new THREE.TorusGeometry(RING.Rf+13,.45,6,96),LM(shade(p.wall,-.25)));cb.rotation.x=Math.PI/2;cb.position.y=.1;world.add(cb);this.curb=cb}
  // the bin for failed videos sits in the middle of the ring
  const bin=new THREE.Group();bin.add(hull(cy(.5,.4,.9,'#6b7280',0,.45,0,10),p.ink,1.07),cy(.55,.55,.1,'#4b5563',0,.95,0,10));bin.position.set(0,0,-2);bin.scale.setScalar(3);bin.add(blob(.8,.2));world.add(bin);this.binLab=null;this.binG=bin;this.relabelBin();
  // gates: a signal post with a round sign facing the camera, and a striped stopper across the belt
  this.bars_={};this.signTex_={};
  [['review',GATE_AT.review],['publish',GATE_AT.publish]].forEach(([k,c])=>{const q=pt3(cToS(c+.03)),ox=Math.cos(q.a),oz=Math.sin(q.a),g=new THREE.Group(),Bo=RING.BW/2+.7;
    g.position.set(q.x+ox*Bo,0,q.z+oz*Bo);g.rotation.y=Math.atan2(-ox,-oz);
    g.add(cy(.1,.12,3.0,'#555',0,1.5,0,7));
    const sign=new THREE.Mesh(new THREE.CircleGeometry(.72,28),new THREE.MeshBasicMaterial({map:this.signTex('stop')}));sign.position.set(0,3.35,.12);g.add(sign);
    const light=sp(.16,'#e5483b',0,2.35,.18,8);light.material=MB('#e5483b');g.add(light);
    const arm=new THREE.Group();arm.position.set(0,.2,Bo);for(let i=0;i<6;i++)arm.add(bx(.34,.42,RING.BW/6,i%2?'#ffffff':p.gate,0,.21,-RING.BW/2+RING.BW/12+i*RING.BW/6));
    g.add(arm);world.add(g);this.bars_[k]={arm,light,sign,open:false,c};
    // where the gate robot stands: beside the post, between belt and house
    const gp=new THREE.Vector3(q.x+ox*(RING.BW/2+3.4)+q.dx*1.6,0,q.z+oz*(RING.BW/2+3.4)+q.dz*1.6);this.pl[k].gate=gp});
  const gk=this.agents[STAGE_ROLE.review],pk=this.agents[STAGE_ROLE.publish];if(gk)gk.guard=this.pl.review.gate;if(pk)pk.guard=this.pl.publish.gate;
  // street lamps along the belt (they glow at night)
  const lampBulb=new THREE.MeshLambertMaterial({color:'#fff3cf',emissive:'#ffd98a',emissiveIntensity:0});this.glow.push(lampBulb);
  for(let i=0;i<14;i++){const a=stAng(STAGES[i>>1])+Math.PI/7+(i&1?.07:-.07),x=(RING.Rb+3.6)*Math.cos(a),z=(RING.Rb+3.6)*Math.sin(a),g=new THREE.Group();g.scale.setScalar(1.7);g.add(cy(.05,.07,3.0,'#4a4f57',0,1.5,0,6),bx(.5,.06,.06,'#4a4f57',.22,3.0,0));
    const bulb=new THREE.Mesh(new THREE.SphereGeometry(.17,10,8),lampBulb);bulb.position.set(.44,2.93,0);g.add(bulb);
    const halo=sprite(this.haloTex(),3.2,3.2,.44,2.93,0);halo.material.blending=THREE.AdditiveBlending;halo.visible=false;this.halos.push(halo);g.add(halo);g.position.set(x,0,z);g.rotation.y=-a;world.add(g)}
  this.nightLights.forEach(l=>world.add(l));
  // decor: the theme's own props fill the middle of the ring
  const dg=this.decorG=new THREE.Group();dg.scale.setScalar(K3);world.add(dg);ex.decor(dg,th,this.anims);
  this.buildAds(world);
  // followed-video marks: ring on the belt + a map pin above the item
  const tg=new THREE.Group(),tr=new THREE.Mesh(new THREE.RingGeometry(1.0,1.3,40),new THREE.MeshBasicMaterial({color:'#2f8fe8',transparent:true,opacity:.95,side:THREE.DoubleSide,depthWrite:false}));tr.rotation.x=-Math.PI/2;tr.position.y=.17;
  const pinS=sprite(this.pinTex(),3.4,4.3,0,6.4,0);pinS.center.set(.5,0);tg.add(tr,pinS);tg.visible=false;world.add(tg);this.trk={g:tg,ring:tr,pin:pinS};
  // shadows: every lit mesh casts and receives, except the big flat ground pieces
  world.traverse(o=>{if(o.isMesh&&o.material&&o.material.isMeshLambertMaterial){o.castShadow=true;o.receiveShadow=true}});flat.forEach(m=>{m.castShadow=false});
  this.buildWorld();this.applyTod();this.bars()},
 signTex(kind){const c=this.signTex_||(this.signTex_={});if(c[kind])return c[kind];
  return c[kind]=ctex(128,128,(g,w,h)=>{g.fillStyle='#fff';g.beginPath();g.arc(64,64,62,0,7);g.fill();g.fillStyle=kind==='stop'?'#e5483b':'#1f9d62';g.beginPath();g.arc(64,64,54,0,7);g.fill();g.strokeStyle='#fff';g.lineWidth=13;g.lineCap='round';g.lineJoin='round';g.beginPath();
   if(kind==='stop'){g.moveTo(34,64);g.lineTo(94,64)}else{g.moveTo(38,66);g.lineTo(56,84);g.lineTo(92,44)}g.stroke()})},
 haloTex(){return this._halo||(this._halo=ctex(64,64,(g,w,h)=>{const gr=g.createRadialGradient(w/2,h/2,1,w/2,h/2,w/2);gr.addColorStop(0,'rgba(255,226,150,.95)');gr.addColorStop(.35,'rgba(255,214,120,.35)');gr.addColorStop(1,'rgba(255,214,120,0)');g.fillStyle=gr;g.fillRect(0,0,w,h)}))},
 pinTex(){return this._pin||(this._pin=ctex(64,80,(g,w,h)=>{g.fillStyle='#2f8fe8';g.strokeStyle='#fff';g.lineWidth=5;g.beginPath();g.moveTo(w/2,h-5);g.bezierCurveTo(w*.02,h*.52,w*.08,7,w/2,7);g.bezierCurveTo(w*.92,7,w*.98,h*.52,w/2,h-5);g.closePath();g.fill();g.stroke();g.fillStyle='#fff';g.beginPath();g.arc(w/2,h*.38,w*.15,0,7);g.fill()}))},
 posterTex(n){const k=((n||1)%5);if(this.posters[k])return this.posters[k];
  const paint=(g,w,h,im)=>{if(im){const r=Math.max(w/im.width,h/im.height);g.drawImage(im,(w-im.width*r)/2,(h-im.height*r)/2,im.width*r,im.height*r);g.fillStyle='rgba(0,0,0,.18)';g.fillRect(0,0,w,h)}else{const gr=GRADS[k],L=g.createLinearGradient(0,0,w*.6,h);L.addColorStop(0,gr[0]);L.addColorStop(1,gr[1]);g.fillStyle=L;g.fillRect(0,0,w,h)}
   g.fillStyle='rgba(255,255,255,.92)';g.fillRect(8,10,w-16,5);g.fillRect(8,19,w*.55,5);g.fillStyle='rgba(0,0,0,.38)';g.beginPath();g.arc(w/2,h*.6,12,0,7);g.fill();g.fillStyle='#fff';g.beginPath();g.moveTo(w/2-4,h*.6-6.5);g.lineTo(w/2+7,h*.6);g.lineTo(w/2-4,h*.6+6.5);g.fill();g.fillStyle='rgba(255,255,255,.9)';g.fillRect(8,h-12,w-16,3)};
  const tex=ctex(64,84,(g,w,h)=>paint(g,w,h,null));
  if(ART.posters[k]){const im=new Image();im.onload=()=>{paint(tex.image.getContext('2d'),64,84,im);tex.needsUpdate=true};im.src=ART.posters[k]}
  return this.posters[k]=tex},
 applyTod(){if(!this.scn)return;const th=this.th,p=th.p,ex=this.ex,n=S.tod==='night',dk=this.dark;
  let top=n?'#050b20':p.sky1,bot=n?mixHex(p.sky2,'#1a2a5c',.72):p.sky2;const W=WX[S.wx||'clear']||{};if(W.sky){const k=W.k*(n?.45:1);top=mixHex(top,W.sky,k);bot=mixHex(bot,W.sky,k)}this.fogk=W.fog||1;
  if(this.bgTex)this.bgTex.dispose();this.bgTex=gradTex(top,bot);this.skyQ.material.map=this.bgTex;this.skyQ.material.needsUpdate=true;this.scn.fog.color.set(bot);
  this.hemi.color.set(n?'#7f93f0':dk?'#8fa0e0':'#ffffff');this.hemi.groundColor.set(n?'#0a1022':(p.ground||ex.ground));this.hemi.intensity=(n?1.35:dk?1.5:2.0)*(W.hemi||1);
  this.sun.color.set(n?'#a9bcff':W.sunc||(dk?'#ffd9a8':'#ffffff'));this.sun.intensity=(n?1.0:dk?1.7:2.4)*(W.sun||1);if(this.groundMesh)this.groundMesh.material.color.set(W.ground?mixHex(ex.ground,W.ground,W.gk):ex.ground);
  this.glow.forEach(m=>{m.emissiveIntensity=n?1.1:0});this.halos.forEach(h=>{h.visible=n});this.nightLights.forEach(l=>{l.intensity=n?26:0});this.glow2.forEach(m=>{m.emissiveIntensity=n?1.5:.8});if(typeof Snd!=='undefined')Snd.env(S.tod,S.wx||'clear');
  this.decorG.children.forEach(o=>{if(o.isMesh&&o.material&&o.material.isMeshBasicMaterial&&o.position.y>=8&&o.geometry&&/Sphere|Circle/.test(o.geometry.type)){if(!o.userData.day)o.userData.day='#'+o.material.color.getHexString();if(th.id!=='dragons'&&th.id!=='cn')o.material.color.set(n?'#e6edff':o.userData.day)}});
  Object.values(this.agents).forEach(a=>{if(a.sprite)a.sprite.material.color.set(n?'#9fb0e0':'#ffffff')});this.applyWx();this.fit()},
 relabelBin(){if(!this.binG)return;if(this.binLab)this.binG.remove(this.binLab);const txt=t('bin')+(S.fails.length?' · '+S.fails.length:'');this.binLab=sprite(labelTex(txt,44),3.4,.64,0,2.0,0);this.binG.add(this.binLab)},
 size(){if(!this.R||!this.canvas)return;const slot=this.canvas.parentElement,w=Math.max(2,slot.clientWidth),h=Math.max(2,slot.clientHeight);this.R.setSize(w,h,false);this.cam.aspect=w/h;this.cam.updateProjectionMatrix();this.fit()},
 fit(){if(!this.canvas||!this.cam)return;const W=Math.max(2,this.canvas.clientWidth),H=Math.max(2,this.canvas.clientHeight),asp=W/H,port=asp<1,tan=Math.tan(this.cam.fov*Math.PI/360)*2,s=this.safe,sw=Math.max(120,W-s.l-s.r),sh=Math.max(120,H-s.t-s.b),shf=port?Math.max(sh,H*.46):sh;
  this.kw=W/(sw*tan*asp);this.kh=H/(shf*tan);this.port=port;const Rw=RING.Rf+HD+20;this.Dw=Math.max(2*Rw*this.kw,2*Rw*.9*this.kh);
  this.cam.setViewOffset(W,H,-(s.l-s.r)/2,-(s.t-s.b)/2,W,H);this.cam.updateProjectionMatrix()},
 setSafe(r){this.safe=r;this.fit()},
 project(v){const rect=this.canvas.getBoundingClientRect(),hr=this.host.getBoundingClientRect(),p=v.clone().project(this.cam);return{x:(p.x*.5+.5)*rect.width+(rect.left-hr.left),y:(-p.y*.5+.5)*rect.height+(rect.top-hr.top),vis:p.z<1}},
 anchor(k){if(k==='bin')return this.binG?new THREE.Vector3(0,7,-2):null;const P=this.pl&&this.pl[k];return P?new THREE.Vector3(P.kx,P.top+3.4,P.kz):null},
 /* --- camera tools: in a house they zoom and peek, in the world they zoom, turn, tilt and move --- */
 tween(d){const o=this.cv;o.idle=0;Object.assign(o.tw,d)},
 zoomBy(f){const o=this.cv;if(S.world)this.tween({wz:clampN(o.wz*f,.08,1.6)});else this.tween({hz:clampN(o.hz*f,.45,1.6)})},
 rotateBy(d){const o=this.cv;if(S.world)this.tween({waz:o.waz+d});else this.tween({haz:clampN(o.haz+d*.9,-.55,.55)})},
 tiltBy(d){const o=this.cv;if(S.world)this.tween({wpol:clampN(o.wpol+d,.3,1.5)});else this.tween({hpol:clampN(o.hpol+d*.5,-.08,.3)})},
 panBy(fwd,right){const o=this.cv,a=o.waz;this.tween({wpx:clampN(o.wpx+Math.cos(a)*right-Math.sin(a)*fwd,-95,95),wpz:clampN(o.wpz-Math.sin(a)*right-Math.cos(a)*fwd,-95,95)})},
 setFx(f){this.fx=f},
 resetView(){const o=this.cv;o.idle=0;if(S.world)o.tw={wz:1,waz:Math.round(o.waz/(2*Math.PI))*2*Math.PI,wpol:1.12,wpx:0,wpz:0};else o.tw={hz:1,haz:0,hpol:0}},
 follow(r){if(r)Twin.go(ROLE_STAGE[r]);else{S.sel=null;S.world=false;Twin.update(true)}},
 flyOver(){Twin.world(true)},
 bindPointer(){const c=this.canvas,o=this.cv;let down=null,last=null;const pts=new Map();
  const wpp=()=>0.9*this.Dw*o.wz/Math.max(300,c.clientHeight);
  const pan=(dx,dy)=>{const a=o.waz,k=wpp();o.wpx=clampN(o.wpx-(Math.cos(a)*dx+Math.sin(a)*dy*1.25)*k,-95,95);o.wpz=clampN(o.wpz-(-Math.sin(a)*dx+Math.cos(a)*dy*1.25)*k,-95,95)};
  c.addEventListener('contextmenu',e=>e.preventDefault());c.addEventListener('pointermove',e=>this.hover(e));c.addEventListener('pointerleave',()=>{this.ptr={x:0,y:0};c.style.cursor=''});
  c.addEventListener('pointerdown',e=>{o.tw={};c.setPointerCapture(e.pointerId);pts.set(e.pointerId,{x:e.clientX,y:e.clientY});down={x:e.clientX,y:e.clientY,haz:o.haz,hpol:o.hpol,waz:o.waz,wpol:o.wpol,moved:0,pinch:false,t:performance.now(),pan:e.button===2||e.shiftKey||e.ctrlKey||e.metaKey};last={x:e.clientX,y:e.clientY};this.dragging=true;o.idle=0});
  c.addEventListener('pointermove',e=>{if(!pts.has(e.pointerId))return;const p=pts.get(e.pointerId);
   if(pts.size===2){const [a,b]=[...pts.values()],d0=Math.hypot(a.x-b.x,a.y-b.y),m0={x:(a.x+b.x)/2,y:(a.y+b.y)/2};p.x=e.clientX;p.y=e.clientY;const [a2,b2]=[...pts.values()],d1=Math.hypot(a2.x-b2.x,a2.y-b2.y),m1={x:(a2.x+b2.x)/2,y:(a2.y+b2.y)/2},f=d0/Math.max(1,d1);if(S.world){o.wz=clampN(o.wz*f,.08,1.6);pan(m1.x-m0.x,m1.y-m0.y)}else o.hz=clampN(o.hz*f,.45,1.6);if(down){down.moved=99;down.pinch=true}return}
   p.x=e.clientX;p.y=e.clientY;if(!down)return;const dx=e.clientX-down.x,dy=e.clientY-down.y;down.moved=Math.max(down.moved,Math.hypot(dx,dy));
   if(S.world){if(down.pan)pan(e.clientX-last.x,e.clientY-last.y);else{o.waz=down.waz-dx*.007;o.wpol=clampN(down.wpol+dy*.0045,.3,1.5)}}
   else{o.haz=clampN(down.haz-dx*.0032,-.55,.55);o.hpol=clampN(down.hpol+dy*.0016,-.08,.3)}last={x:e.clientX,y:e.clientY}});
  const up=e=>{pts.delete(e.pointerId);if(down&&pts.size===0&&e.button!==2&&!down.pinch){const dx=e.clientX-down.x,dy=e.clientY-down.y,dtm=performance.now()-down.t;
    if(down.moved<6)this.pick(e);else if(!S.world&&Math.abs(dx)>Math.abs(dy)*1.2&&(Math.abs(dx)>70||(Math.abs(dx)>34&&dtm<260)))Twin.hstep(dx<0?1:-1)}
   if(pts.size===0){down=null;this.dragging=false;o.idle=0}};c.addEventListener('pointerup',up);c.addEventListener('pointercancel',up);
  c.addEventListener('wheel',e=>{e.preventDefault();o.tw={};const f=Math.exp(e.deltaY*(e.ctrlKey?.01:.0015));if(S.world)o.wz=clampN(o.wz*f,.08,1.6);else o.hz=clampN(o.hz*f,.45,1.6)},{passive:false});
  c.addEventListener('dblclick',()=>this.resetView());
  this.keyH=e=>{if(!this.host||!this.host.matches(':hover')&&document.activeElement!==c)return;if(/INPUT|TEXTAREA|SELECT/.test((e.target||{}).tagName)||e.metaKey||e.ctrlKey||e.altKey)return;const k=e.key.toLowerCase(),st=14*o.wz*(e.shiftKey?2:1);
   const common={'+':()=>this.zoomBy(1/1.2),'=':()=>this.zoomBy(1/1.2),'-':()=>this.zoomBy(1.2),r:()=>this.resetView(),m:()=>Twin.world(),escape:()=>{if(S.world)Twin.world(false)}};
   const house={arrowleft:()=>Twin.hstep(-1),arrowright:()=>Twin.hstep(1),a:()=>Twin.hstep(-1),d:()=>Twin.hstep(1)};
   const wmap={w:()=>this.panBy(st,0),arrowup:()=>this.panBy(st,0),s:()=>this.panBy(-st,0),arrowdown:()=>this.panBy(-st,0),a:()=>this.panBy(0,-st),arrowleft:()=>this.panBy(0,-st),d:()=>this.panBy(0,st),arrowright:()=>this.panBy(0,st),q:()=>this.rotateBy(-.25),e:()=>this.rotateBy(.25),f:()=>this.tiltBy(-.15),g:()=>this.tiltBy(.15)};
   const fn=common[k]||(S.world?wmap[k]:house[k]);if(fn){e.preventDefault();fn()}};window.addEventListener('keydown',this.keyH)},
 pick(e){const r=this.canvas.getBoundingClientRect(),m=new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-((e.clientY-r.top)/r.height)*2+1),rc=new THREE.Raycaster();rc.setFromCamera(m,this.cam);
  const vis=o=>{for(;o;o=o.parent)if(!o.visible)return false;return true};
  if(!S.world){
   const ih=rc.intersectObjects([...this.items.values()],true);if(ih.length){let o=ih[0].object;while(o&&!o.userData.itemId)o=o.parent;if(o){S.track=o.userData.itemId;S.sel=null;Twin.update(true);return}}
   const ah=rc.intersectObjects(Object.values(this.agents).filter(a=>a.g.visible).map(a=>a.g),true);if(ah.length){let o=ah[0].object;while(o&&!o.userData.role)o=o.parent;if(o){Chat.open(o.userData.role);return}}
   const th=rc.intersectObjects(this.acts.filter(vis),false);if(th.length){const f=th[0].object.userData.act;if(f){f();return}}
   const ad=rc.intersectObjects(this.adObjs.filter(vis),true);if(ad.length){let o=ad[0].object;while(o&&!o.userData.adSlot)o=o.parent;if(o){ADS.sel=o.userData.adSlot;go('ads');return}}}
  const hits=rc.intersectObjects(this.kiosks.filter(g=>g.visible),true);if(hits.length){let o=hits[0].object;while(o&&!o.userData.stage)o=o.parent;if(o){if(S.world)Twin.go(o.userData.stage);else Twin.select(o.userData.stage)}}},
 /* the pointer: leans the view a little and turns the cursor into a hand over things you can tap */
 hover(e){const r=this.canvas.getBoundingClientRect();this.ptr={x:((e.clientX-r.left)/r.width)*2-1,y:((e.clientY-r.top)/r.height)*2-1};if(S.world||this.dragging)return;const now=performance.now();if(now-(this._hv||0)<90)return;this._hv=now;
  const m=new THREE.Vector2(this.ptr.x,-this.ptr.y),rc=new THREE.Raycaster();rc.setFromCamera(m,this.cam);const vis=o=>{for(;o;o=o.parent)if(!o.visible)return false;return true};
  const h=rc.intersectObjects(this.acts.filter(vis),false).length||rc.intersectObjects(this.adObjs.filter(vis),true).length;this.canvas.style.cursor=h?'pointer':''},
 /* --- sim bridge --- */
 place(c){const a=SIM.anchors['3d'],i=Math.min(7,Math.floor(c)),f=a[i]+(a[i+1]-a[i])*(c-i);return pt3(f*PATH3.L)},
 bars(){if(!this.scn)return;['review','publish'].forEach(k=>{const b=this.bars_[k];if(!b)return;const waiting=(k==='review'?S.queue:S.pubq).some(x=>x.sim);b.open=!waiting;b.light.material.color.set(b.open?'#2fbf71':'#e5483b');b.sign.material.map=this.signTex(b.open?'go':'stop');b.sign.material.needsUpdate=true});
  ['gatekeeper','poster'].forEach((r,i)=>{const a=this.agents[r],k=i?'publish':'review';if(!a)return;const waiting=(k==='review'?S.queue:S.pubq).some(x=>x.sim);if(waiting&&!S.reduce)a.mode='guard';else if(a.mode==='guard')a.mode='home'})},
 wantRoom(k){const st=this.subSt&&this.subSt[k];if(!st)return -1;let i=st.indexOf('cur');if(i<0)i=st.indexOf('wait');return i},
 clearBubbles(){this.bubs.forEach(b=>{b.el.remove();b.dead=true});this.bubs=[]},
 bubble(ev){if(!ev.stage||this.hidden)return;const role=STAGE_ROLE[ev.stage],a=this.agents[role];
  if(a&&!S.reduce){if(ev.kind==='gate.review'||ev.kind==='gate.publish'){a.mode='guard'}else{const w=this.wantRoom(ev.stage);a.mode='work';a.t=0;a.wi=w>=0?w:a.pi;a.work=a.pat[a.wi];a.workDur=ev.kind==='make.started'?2.2:1.4}}
  if(role==='reflector'&&this.agents.evolver&&!S.reduce&&ev.kind==='hints.generated'){const e=this.agents.evolver;e.mode='bounce';e.t=0;e.wi=e.pi;e.work=e.pat[e.pi]}
  if(S.world||ev.stage!==(this.fx&&this.fx.sel))return;
  const old=this.bubs.filter(b=>!b.dead);while(old.length>=2){const b=old.shift();b.el.remove();b.dead=true}
  const el=document.createElement('div');el.className='bubble';el.style.setProperty('--bub',SC[ev.stage]);el.innerHTML=`<b>${esc(charName(role))}</b>${esc(phrase(ev))}`;this.host.appendChild(el);
  const b={el,role,born:performance.now(),dead:false,slot:old.length};this.bubs.push(b);const life=S.keep?1e9:S.reduce?5200:3900;b.life=life},
 /* --- one frame --- */
 draw(dt){if(!this.R||!this.scn)return;this.clock+=dt;const T=this.clock,dtt=Math.min(dt,.05),fx=this.fx||{};
  this.beltTex.offset.x-=dt*(S.loop==='running'?SPEED/PX3/1.6:0);
  // items on the belt
  const live=SIM.items;for(const [id,g] of this.items)if(!live.some(i=>i.id===id)){this.world.remove(g);this.items.delete(id)}
  for(const it of live){let g=this.items.get(it.id);if(!g){g=this.mkItem(it);g.userData.itemId=it.id;this.world.add(g);this.items.set(it.id,g)}
    const q=this.place(Math.min(it.c,7.999));g.position.set(q.x,.14+.39*RING.ITS+Math.sin(T*3+it.n)*.03,q.z);g.rotation.y=Math.atan2(q.dx,q.dz)-Math.PI/2;
    const col=it.cracked?'#7a1f1f':STATECOL[it.state]||'#999';g.userData.body.material.color.set(col);g.userData.body.material.emissive.set(col);g.userData.body.material.emissiveIntensity=S.tod==='night'?.4:0;g.userData.gold.visible=!!(it.gold&&['published','measured','archived'].includes(it.state));g.userData.crack.visible=!!it.cracked;
    if(g.userData.gold.visible)g.userData.gold.material.opacity=.45+Math.sin(T*4)*.25;
    const o=it.dead?Math.max(0,1-it.fade):1;g.traverse(m=>{if(m.material&&m.material!==g.userData.gold.material){m.material.transparent=o<1;m.material.opacity=o}})}
  // camera first: it decides which houses are visible
  const e=this.cameraStep(dt,T);
  // plates under houses: selected / needs you
  for(const k in this.rings){const R=this.rings[k],need=fx.need&&fx.need[k],tgt=e>.3?(need?.9:fx.sel===k?.6:0):0;R.v+=(tgt-R.v)*Math.min(1,dt*8);R.rm.color.set(need?'#e0a21a':SC[k]);R.dm.color.copy(R.rm.color);R.rm.opacity=R.v*(need&&!S.reduce?.5+.3*Math.sin(T*4):.7);R.dm.opacity=R.v*.2;R.g.scale.setScalar(S.reduce?1:1+Math.sin(T*3.2)*.015)}
  // followed video: ring, pin and the ribbon it already travelled
  const ti=fx.track&&SIM.items.find(i=>i.id===fx.track&&!i.dead),tk=this.trk;
  if(tk){tk.g.visible=!!ti;this.trail.visible=!!ti;if(ti){const cc=Math.min(ti.c,7.999),q=this.place(cc),a=SIM.anchors['3d'],ii=Math.floor(cc),f=a[ii]+(a[ii+1]-a[ii])*(cc-ii);tk.g.position.set(q.x,0,q.z);const sc=(1+Math.sin(T*4)*.07)*2.6;tk.ring.scale.set(sc,sc,sc);tk.ring.material.opacity=.7+Math.sin(T*4)*.25;tk.pin.position.y=6.4+Math.sin(T*3)*.3;this.trail.geometry.setDrawRange(0,Math.max(0,Math.floor(f*this.N))*6)}this.dashTex.offset.x-=dt*.5}
  // rooms: one lamp and one rug per sub-step, on every house
  const it0=fx.track&&SIM.items.find(i=>i.id===fx.track&&!i.dead);this.subSt={};
  for(const k of STAGES){const st=this.subSt[k]=Twin.subs(k,it0),ls=this.bldLamps[k],rl=this.roofLamps[k],rugs=this.rugs[k];
    const paint=(l,s0)=>{const m=l.material;if(s0==='done'){m.color.set(SC[k]);m.emissive.set(SC[k]);m.emissiveIntensity=.8}else if(s0==='cur'||s0==='wait'){const a=S.reduce?1:.6+.4*Math.sin(T*6);m.color.set('#ffc247');m.emissive.set('#ffb21f');m.emissiveIntensity=a*(s0==='wait'?1.1:1)}else{m.color.set('#8c97a4');m.emissive.set('#000000');m.emissiveIntensity=0}};
    if(ls)ls.forEach((l,i)=>paint(l,st[i]||'todo'));if(rl)rl.forEach((l,i)=>paint(l,st[i]||'todo'));
    if(rugs)rugs.forEach((r,i)=>{const s0=st[i]||'todo',m=r.material;if(s0==='done')m.color.set(shade(SC[k],.45));else if(s0==='cur'||s0==='wait')m.color.set(mixHex(r.userData.base,'#ffc247',S.reduce?.8:.55+.3*Math.sin(T*5)));else m.color.set(r.userData.base)})}
  // gates
  for(const k in this.bars_){const b=this.bars_[k],target=b.open?.05:1;b.arm.scale.y+=(target-b.arm.scale.y)*Math.min(1,dt*6)}
  // agents and the living world
  this.drawWorld(T,dtt);for(const r in this.agents)this.stepAgent(this.agents[r],dtt,T);
  this.anims.forEach(fn=>fn(T,dtt));this.fxStep(dtt);
  // labels grow when you look from far
  for(const k of STAGES){const L=this.labels[k],ic=this.icons[k];if(L){const s=lerp(1,3.8,e);L.scale.set(8*s,1.5*s,1);L.position.y=this.pl[k].top+1.9*s;ic.visible=e>.3&&this.pl[k].g.visible;ic.position.y=this.pl[k].top+4.4*s;ic.scale.set(3*s,3*s,1)}}
  this.R.clear();this.R.render(this.bgScn,this.bgCam);this.R.clearDepth();this.R.render(this.scn,this.cam);
  // speech bubbles follow the robot of the house in front
  const rect=this.canvas.getBoundingClientRect(),hr=this.host.getBoundingClientRect(),now=performance.now(),v=new THREE.Vector3();
  this.bubs=this.bubs.filter(b=>{if(b.dead){return false}const age=now-b.born;if(age>b.life+500||S.world){b.el.remove();return false}if(age>b.life)b.el.classList.add('out');
    const a=this.agents[b.role];if(!a)return true;v.copy(a.g.position);v.y+=3.2;v.project(this.cam);const x=(v.x*.5+.5)*rect.width+(rect.left-hr.left),y=(-v.y*.5+.5)*rect.height+(rect.top-hr.top)-(b.slot?64:0);
    b.el.style.left=Math.max(70,Math.min(hr.width-70,x))+'px';b.el.style.top=Math.max(this.safe.t+(b.el.offsetHeight||56)+8,y)+'px';return true})},
 /* the camera: stands in front of the focused house, or hovers over the whole ring; returns how far into the world view it is (0..1) */
 cameraStep(dt,T){const o=this.cv,fx=this.fx||{},k=1-Math.exp(-dt*5),kl=1-Math.exp(-dt*2.2),fk=this.pl[fx.sel]?fx.sel:'review',P=this.pl[fk];
  if(o.fa==null)o.fa=P.a;if(fk!==this.lastFocus){this.lastFocus=fk;this.clearBubbles();if(typeof Snd!=='undefined')Snd.scene(S.world?'world':fk)}
  if(this.worldSnd!==!!S.world){this.worldSnd=!!S.world;if(typeof Snd!=='undefined')Snd.scene(S.world?'world':fk)}
  let da=P.a-o.fa;da=Math.atan2(Math.sin(da),Math.cos(da));o.fa+=da*k;
  o.wm+=((S.world?1:0)-o.wm)*(1-Math.exp(-dt*3.4));const e=o.wm*o.wm*(3-2*o.wm);
  o.idle+=dt;for(const p in o.tw){o[p]+=(o.tw[p]-o[p])*k;if(Math.abs(o.tw[p]-o[p])<.002){o[p]=o.tw[p];delete o.tw[p]}}
  if(!this.dragging&&o.idle>1.4&&!S.world){const pp=this.ptr||{x:0,y:0};o.haz+=(pp.x*.1-o.haz)*kl;o.hpol+=(-pp.y*.03-o.hpol)*kl}
  const ua=Math.cos(o.fa),ub=Math.sin(o.fa),rx=-ub,rz=ua;
  // in front of the house
  const Wv=this.port?Math.min(P.W,RW*1.7)+3.2:P.W+(this.painted?12:4.5),Hv=Math.min(P.top,P.Ht+3.6)+4.8,dT=Math.max(Wv*this.kw,Hv*this.kh)*o.hz;o.hd=o.hd==null?dT:o.hd+(dT-o.hd)*k;
  const ag=this.agents[STAGE_ROLE[fk]],rl=ag?(ag.g.position.x-P.kx)*rx+(ag.g.position.z-P.kz)*rz:0,lim=Math.max(0,P.W/2-Wv/2+.5);o.lat+=(clampN(rl,-lim,lim)*(this.port?1:.15)-o.lat)*kl;
  const ty=(Math.min(P.top,P.Ht+3.6)-1.2)*.5,Tx=RING.Rf*ua-ua*.5+rx*o.lat,Tz=RING.Rf*ub-ub*.5+rz*o.lat,ph=.15+o.hpol,az=o.haz+(S.reduce?0:Math.sin(T*.3)*.025),d=o.hd,hx=-ua*d*Math.cos(ph),hz=-ub*d*Math.cos(ph),cs=Math.cos(az),sn=Math.sin(az);
  const Hc=new THREE.Vector3(Tx+hx*cs+hz*sn,ty+d*Math.sin(ph),Tz-hx*sn+hz*cs),Hl=new THREE.Vector3(Tx,ty,Tz);
  // above the whole world
  const Dw=this.Dw*o.wz,wa=o.waz,wp=o.wpol,Wc=new THREE.Vector3(o.wpx+Dw*Math.cos(wp)*Math.sin(wa),Dw*Math.sin(wp),o.wpz+Dw*Math.cos(wp)*Math.cos(wa)),Wl=new THREE.Vector3(o.wpx,0,o.wpz);
  const C=Hc.clone().lerp(Wc,e),Lk=Hl.clone().lerp(Wl,e);this.cam.position.copy(C);this.cam.lookAt(Lk);
  // fog and stage light follow the camera
  const fog=this.scn.fog,fk2=this.fogk||1;fog.near=lerp(d+10,Dw*1.1,e)*fk2;fog.far=lerp(d+110,Dw*3.4,e)*fk2;
  const sunH=new THREE.Vector3(Tx-ua*16-rx*13,30,Tz-ub*16-rz*13),sunW=new THREE.Vector3(-70,120,70),tgtH=new THREE.Vector3(Tx,0,Tz);
  this.sun.position.copy(sunH.lerp(sunW,e));this.sun.target.position.copy(tgtH.lerp(new THREE.Vector3(0,0,0),e));this.sun.target.updateMatrixWorld();
  const half=lerp(24,100,e),sc=this.sun.shadow.camera;if(Math.abs(sc.right-half)>.05){sc.left=-half;sc.right=half;sc.top=half;sc.bottom=-half;sc.far=lerp(110,420,e);sc.updateProjectionMatrix()}
  // only the houses near the focus are drawn from the street; the far ones are hidden
  for(const kk of STAGES){const Pk=this.pl[kk];let dd=Pk.a-o.fa;dd=Math.abs(Math.atan2(Math.sin(dd),Math.cos(dd)));const vis=e>.02||dd<1.15;if(Pk.scn)Pk.scn.userData.terrain.visible=e<.02&&dd<.5;Pk.g.visible=vis;Pk.rg.visible=vis;Pk.label.visible=vis&&e>.25;
    for(const r in this.agents){const a=this.agents[r];if(a.k===kk)a.g.visible=vis}}
  this.decorG.visible=this.lake.visible=this.binG.visible=this.adWorld.visible=e>.02;this.adRepaint();this.life.visible=e<.6;const nb=Object.keys(this.backs).length;this.hills.visible=e<.5&&!nb;
  this.farOn=!this.painted||e>.02;this.groundMesh.visible=this.farOn;if(this.plazaM)this.plazaM.visible=this.farOn;if(this.curb)this.curb.visible=this.farOn;this.trees.visible=this.farOn&&(S.wx||'clear')!=='desert';this.cacti.visible=this.farOn&&S.wx==='desert';
  if(this.painted){this.cam.updateMatrixWorld();const pe=new THREE.Vector3((RING.Rf+HD/2+.2+15)*ua,0,(RING.Rf+HD/2+.2+15)*ub).project(this.cam),W=this.canvas.clientWidth,H=this.canvas.clientHeight,asp=W/H,Th=Math.tan(this.cam.fov*Math.PI/360)*asp,wx=WX[S.wx||'clear']||{},nt=S.tod==='night';
    const Wp=Math.max(W,H*16/9),Hp=Wp*9/16,wN=2*Wp/W,hN=2*Hp/H;
    for(const kk in this.backs){const bk=this.backs[kk];let dd=o.fa-this.pl[kk].a;dd=Math.atan2(Math.sin(dd),Math.cos(dd));const op=e>.02?0:Math.max(0,Math.min(1,1-(Math.abs(dd)-.2)/.4));bk.q.visible=op>.01;if(!bk.q.visible)continue;
      bk.m.opacity=op;bk.q.scale.set(wN/2,hN/2,1);bk.q.position.x=-Math.tan(dd)/Th*.9;bk.q.position.y=pe.y+(this.ROWS[kk]-.5)*hN;bk.m.color.set(nt?'#56649e':wx.sky?mixHex('#ffffff',wx.sky,(wx.k||0)*.55):'#ffffff')}}
  // life frame (clouds, birds, plane) hangs behind the focused house
  this.life.position.set((RING.Rf+HD/2)*ua,0,(RING.Rf+HD/2)*ub);this.life.rotation.y=Math.atan2(-ua,-ub);
  this.wxc={x:lerp(Tx-ua*d*.2+ua*22,o.wpx,e),z:lerp(Tz-ub*d*.2+ub*22,o.wpz,e),s:1+e*1.8};
  return e},
 mkItem(it){const g=new THREE.Group(),body=hull(bx(.56,.78,.3,'#999',0,0,0),'#0f2233',1.08),poster=new THREE.Mesh(new THREE.PlaneGeometry(.42,.54),new THREE.MeshBasicMaterial({map:this.posterTex(it&&it.n)}));poster.position.set(0,.06,.153);g.add(body,poster,sp(.04,'#0f2233',-.12,-.31,.16,6),sp(.04,'#0f2233',.12,-.31,.16,6),new THREE.Mesh(new THREE.SphereGeometry(.9,8,6),new THREE.MeshBasicMaterial({visible:false})));
  const gold=sprite(ctex(64,64,(c,w,h)=>{const gr=c.createRadialGradient(w/2,h/2,2,w/2,h/2,w/2);gr.addColorStop(0,'rgba(255,226,122,.95)');gr.addColorStop(1,'rgba(255,226,122,0)');c.fillStyle=gr;c.fillRect(0,0,w,h)}),1.9,1.9,0,0,0);gold.material.opacity=.6;gold.visible=false;g.add(gold);
  const crack=bx(.04,.6,.32,'#fff',0,0,0);crack.rotation.z=.5;crack.visible=false;g.add(crack);g.userData={body,gold,crack};g.scale.setScalar(RING.ITS);g.add(blob(.4,.2));g.children[g.children.length-1].position.y=-.48;return g},
 /* robots pace the rooms of their house, side to side; they work where the followed video is */
 stepAgent(a,dt,T){const L=a.limbs,n=a.pat.length,want=this.wantRoom(a.k);let tgt;
  if(a.mode==='guard'&&a.guard)tgt=a.guard;else if((a.mode==='work'||a.mode==='bounce')&&a.work)tgt=a.work;
  else{ // idle: walk the rooms
    if(S.reduce){a.pi=want>=0?want:0;a.arrived=true}
    else if(a.arrived){a.dw-=dt;if(a.dw<=0){let ni;
      if(want>=0){if(a.pi===want){const o2=[want-1,want+1].filter(v=>v>=0&&v<n);ni=o2.length?o2[Math.floor(Math.random()*o2.length)]:want}else ni=want}
      else{ni=a.pi+a.dir;if(ni<0||ni>=n){a.dir=-a.dir;ni=a.pi+a.dir}}
      if(ni!==a.pi||want<0){a.pi=Math.max(0,Math.min(n-1,ni));a.arrived=false}else a.dw=1.5}}
    tgt=a.pat[a.pi]}
  const gp=a.g.position;if(S.reduce){gp.copy(tgt)}
  const d=Math.hypot(tgt.x-gp.x,tgt.z-gp.z),walking=d>.08;
  if(walking){const sp2=2.8*dt,kk=Math.min(1,sp2/d);gp.x+=(tgt.x-gp.x)*kk;gp.z+=(tgt.z-gp.z)*kk;const ang=Math.atan2(tgt.x-gp.x,tgt.z-gp.z);let da=ang-a.g.rotation.y;da=Math.atan2(Math.sin(da),Math.cos(da));a.g.rotation.y+=da*Math.min(1,dt*10);a.ph+=dt*9}
  else{let da=this.pl[a.k].ry-a.g.rotation.y;da=Math.atan2(Math.sin(da),Math.cos(da));a.g.rotation.y+=da*Math.min(1,dt*6);
   if(!a.arrived&&a.mode==='home'){a.arrived=true;a.dw=(a.pi===want?3.2:1.1+Math.random()*1.2);a.busy=a.pi===want||Math.random()<.5}
   if(a.mode==='work'||a.mode==='bounce'){a.t+=dt;if(a.t>a.workDur){a.mode='home';a.t=0;if(a.wi!=null)a.pi=a.wi;a.arrived=true;a.dw=1}}}
  gp.y+=((tgt.y||0)-gp.y)*Math.min(1,dt*8);
  const working=!walking&&(a.mode==='work'||a.mode==='bounce'||(a.mode==='home'&&a.busy&&a.arrived));
  if(a.sprite){a.sprite.position.y=(a.sy||1.2)+(walking?Math.abs(Math.sin(a.ph))*.14:Math.sin(T*2+a.ph)*.02);a.sprite.material.rotation=walking?Math.sin(a.ph)*.07:(working?Math.sin(T*8)*.04:0);return}
  const sw=walking?Math.sin(a.ph):0;
  L.legL.rotation.x=sw*.75;L.legR.rotation.x=-sw*.75;L.armL.rotation.x=-sw*.6;L.armR.rotation.x=working?-1.5+Math.sin(T*10)*.55:sw*.6;
  if(a.mode==='guard'&&!walking){L.armR.rotation.x=-.2;L.armL.rotation.x=0}
  L.body.position.y=walking?Math.abs(Math.sin(a.ph))*.07:(working?Math.abs(Math.sin(T*10))*.04:Math.sin(T*2+a.ph)*.012);
  if(a.bulb){a.bulb.scale.setScalar(1+Math.sin(T*3)*.08)}if(a.paddle){a.paddle.forEach(m=>m.visible=true)}}
};
