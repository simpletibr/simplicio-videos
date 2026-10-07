/* ===== 3D factory (Three.js, procedural low-poly, theme-driven). Agents walk, the belt runs, gates open. ===== */
const K3=1.78,BS=2.0,AG=1.25,PX3=34;   // town scale, building scale, agent scale, belt pixels per world unit
const W3={A:16,B:8.5,R:3,BW:2.1};
const PATH3=(()=>{const {A,B,R}=W3,segs=[];let L=0;
  const line=(x0,z0,x1,z1)=>{const len=Math.hypot(x1-x0,z1-z0);segs.push({t:'l',x0,z0,x1,z1,len,s0:L});L+=len};
  const arc=(cx,cz,a0,a1)=>{const len=Math.abs(a1-a0)*R;segs.push({t:'a',cx,cz,a0,a1,len,s0:L});L+=len};
  line(-A+R,-B,A-R,-B);arc(A-R,-B+R,-Math.PI/2,0);line(A,-B+R,A,B-R);arc(A-R,B-R,0,Math.PI/2);
  line(A-R,B,-A+R,B);arc(-A+R,B-R,Math.PI/2,Math.PI);line(-A,B-R,-A,-B+R);arc(-A+R,-B+R,Math.PI,Math.PI*1.5);
  return {segs,L}})();
function pt3(s){const L=PATH3.L;s=((s%L)+L)%L;const g=PATH3.segs.find(q=>s<=q.s0+q.len)||PATH3.segs[PATH3.segs.length-1],t=Math.min(1,(s-g.s0)/g.len);
  if(g.t==='l'){const dx=(g.x1-g.x0)/g.len,dz=(g.z1-g.z0)/g.len;return{x:g.x0+(g.x1-g.x0)*t,z:g.z0+(g.z1-g.z0)*t,dx,dz}}
  const a=g.a0+(g.a1-g.a0)*t;return{x:g.cx+W3.R*Math.cos(a),z:g.cz+W3.R*Math.sin(a),dx:-Math.sin(a),dz:Math.cos(a)}}
const ST3={brand:{s:3.25,side:'top'},ideas:{s:9.75,side:'top'},make:{s:16.25,side:'top'},review:{s:22.75,side:'top'},publish:{s:36.21,side:'right'},metrics:{s:52.92,side:'bottom'},report:{s:65.92,side:'bottom'}};
const GATE_S={review:20.5,publish:31.6};
function geo3(){const a=[0];STAGES.forEach(k=>a.push(ST3[k].s/PATH3.L));a.push(1);SIM.anchors['3d']=a;SIM.len['3d']=PATH3.L*PX3}

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
const SceneThree={host:null,hidden:false,variant:'3d',charPos:{},R:null,scn:null,cam:null,canvas:null,ro:null,items:new Map(),agents:{},bubs:[],anims:[],tex:{},bars_:{},orb:{az:0,pol:0,zoom:1,px:0,pz:0,drag:null,idle:0,to:null},safe:{l:0,t:0,r:0,b:0},fx:{track:null,sel:null,need:{}},bin:null,clock:0,kiosks:[],
 mount(h){if(!THREE_OK())return;this.host=h;h.dataset.mode='3d';const slot=$('.slot',h);this.canvas=document.createElement('canvas');this.canvas.className='three';slot.appendChild(this.canvas);
  this.R=new THREE.WebGLRenderer({canvas:this.canvas,antialias:!Q.get('lowfx'),alpha:false,powerPreference:'high-performance'});this.R.setPixelRatio(Math.min(window.devicePixelRatio||1,2));this.R.shadowMap.enabled=true;this.R.shadowMap.type=THREE.PCFSoftShadowMap;
  this.build();this.size();this.ro=('ResizeObserver' in window)?new ResizeObserver(()=>this.size()):null;if(this.ro)this.ro.observe(slot);this.bindPointer()},
 unmount(){if(this.keyH){window.removeEventListener('keydown',this.keyH);this.keyH=null}if(this.ro)this.ro.disconnect();this.ro=null;if(this.scn){this.scn.traverse(o=>{if(o.geometry)o.geometry.dispose();const m=o.material;if(m){(Array.isArray(m)?m:[m]).forEach(x=>{if(x.map)x.map.dispose();x.dispose()})}})}
  if(this.bgTex){this.bgTex.dispose();this.bgTex=null}if(this.R){this.R.dispose();this.R.forceContextLoss&&this.R.forceContextLoss()}this.R=null;this.scn=null;this.items.clear();this.agents={};this.bubs.forEach(b=>b.el.remove());this.bubs=[];this.anims=[];this.host=null;this.kiosks=[];this.canvas=null},
 build(){const th=TCUR(),p=th.p,ex=TH3[th.id],style=S.view==='3d-sprites'?'sprite':'model';
  this.anims=[];this.items.clear();this.agents={};this.kiosks=[];this.glow=[];this.halos=[];this.rings={};this.posters={};this.th=th;this.ex=ex;this.dark=['ru','dragons'].includes(th.id);
  const sc=this.scn=new THREE.Scene();sc.fog=new THREE.Fog(p.sky2,38,92);
  this.hemi=new THREE.HemisphereLight('#ffffff',p.ground||ex.ground,2.0);
  const sun=this.sun=new THREE.DirectionalLight('#ffffff',2.4);sun.position.set(-16,30,16);sun.target.position.set(1.6,0,-3.7);sun.castShadow=true;
  const shd=sun.shadow;shd.mapSize.set(Q.get('lowfx')?1024:3072,Q.get('lowfx')?1024:3072);Object.assign(shd.camera,{left:-46,right:46,top:40,bottom:-34,near:2,far:120});shd.bias=-.0004;shd.normalBias=.035;shd.radius=3;
  sc.add(this.hemi,sun,sun.target);
  const cam=this.cam=new THREE.PerspectiveCamera(36,16/9,.1,200);
  const world=new THREE.Group();sc.add(world);this.world=world;
  const flat=[];
  const ground=this.groundMesh=new THREE.Mesh(new THREE.CircleGeometry(130,48),LM(ex.ground));ground.rotation.x=-Math.PI/2;world.add(ground);flat.push(ground);
  // plaza
  const sh=new THREE.Shape(),ax=W3.A+7,bz=W3.B+7.5,r=W3.R+5;sh.moveTo(-ax+r,-bz);sh.lineTo(ax-r,-bz);sh.absarc(ax-r,-bz+r,r,-Math.PI/2,0,false);sh.lineTo(ax,bz-r);sh.absarc(ax-r,bz-r,r,0,Math.PI/2,false);sh.lineTo(-ax+r,bz);sh.absarc(-ax+r,bz-r,r,Math.PI/2,Math.PI,false);sh.lineTo(-ax,-bz+r);sh.absarc(-ax+r,-bz+r,r,Math.PI,Math.PI*1.5,false);
  const pt=ctex(512,512,ex.plaza);pt.wrapS=pt.wrapT=THREE.RepeatWrapping;if(th.id==='br'&&ART.plaza){const im=new Image();im.onload=()=>{pt.image.getContext('2d').drawImage(im,0,0,512,512);pt.needsUpdate=true};im.src=ART.plaza}pt.repeat.set(1/3.6,1/3.6);const plaza=new THREE.Mesh(new THREE.ShapeGeometry(sh,24),new THREE.MeshLambertMaterial({map:pt}));plaza.rotation.x=-Math.PI/2;plaza.position.y=.01;world.add(plaza);flat.push(plaza);
  // belt
  const N=this.N=Math.ceil(PATH3.L/.2),pos=[],uv=[],idx=[],pos2=[],pos3=[];for(let i=0;i<=N;i++){const s=PATH3.L*i/N,q=pt3(s),nx=-q.dz,nz=q.dx,w=W3.BW/2;pos.push(q.x+nx*w,.12,q.z+nz*w,q.x-nx*w,.12,q.z-nz*w);pos2.push(q.x+nx*(w+.22),.06,q.z+nz*(w+.22),q.x-nx*(w+.22),.06,q.z-nz*(w+.22));pos3.push(q.x+nx*.26,.17,q.z+nz*.26,q.x-nx*.26,.17,q.z-nz*.26);uv.push(s,0,s,1);if(i<N){const a=i*2;idx.push(a,a+1,a+2,a+1,a+3,a+2)}}
  const mk=(P,U,mat)=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(P,3));if(U)g.setAttribute('uv',new THREE.Float32BufferAttribute(U,2));g.setIndex(idx);g.computeVertexNormals();return new THREE.Mesh(g,mat)};
  world.add(mk(pos2,null,new THREE.MeshBasicMaterial({color:p.ink,side:THREE.DoubleSide})));
  const bt=this.beltTex=ctex(128,128,(g,w,h)=>{g.fillStyle=p.belt;g.fillRect(0,0,w,h);g.fillStyle=shade(p.belt,.18);for(let x=0;x<w;x+=w/4)g.fillRect(x,6,6,h-12);g.fillStyle=p.line;g.fillRect(0,5,w,3);g.fillRect(0,h-8,w,3)});bt.wrapS=THREE.RepeatWrapping;
  const belt=mk(pos,uv,new THREE.MeshLambertMaterial({map:bt,side:THREE.DoubleSide}));world.add(belt);flat.push(belt);
  // the path the followed video already travelled (a flowing blue ribbon on the belt)
  const dt=this.dashTex=ctex(64,8,(g,w,h)=>{g.fillStyle='#2f8fe8';g.fillRect(0,0,w,h);g.fillStyle='#bfe3ff';g.fillRect(0,2,w*.5,h-4)});dt.wrapS=THREE.RepeatWrapping;dt.repeat.set(1.4,1);
  const trail=this.trail=mk(pos3,uv,new THREE.MeshBasicMaterial({map:dt,transparent:true,opacity:.92,depthWrite:false,side:THREE.DoubleSide}));trail.geometry.setDrawRange(0,0);trail.renderOrder=2;world.add(trail);
  // stations
  const place=(k)=>{const q=pt3(ST3[k].s),side=ST3[k].side,D=4.4;let kx,kz,ry=0,hx,hz,wx,wz,gx,gz;
    if(side==='top'){kx=q.x;kz=q.z-D;hx=q.x+2.0;hz=q.z-2.0;wx=q.x+.8;wz=q.z-1.7;gx=q.x+.7;gz=q.z-1.8}
    else if(side==='right'){kx=q.x+D;kz=q.z;ry=-Math.PI/2;hx=q.x+2.0;hz=q.z+2.0;wx=q.x+1.7;wz=q.z+.8;gx=q.x+1.8;gz=q.z-.7}
    else{kx=q.x;kz=q.z-D;hx=q.x-2.0;hz=q.z-2.0;wx=q.x-.8;wz=q.z-1.7;gx=q.x;gz=q.z-1.8}
    return{q,kx,kz,ry,hx,hz,wx,wz,gx,gz}};
  this.pl={};
  const wm=this.winMat=new THREE.MeshLambertMaterial({color:'#dff1ff',emissive:'#ffcf7a',emissiveIntensity:0,flatShading:true});this.glow.push(wm);
  const winG=new THREE.BoxGeometry(.4,.4,.05),winS=new THREE.BoxGeometry(.05,.4,.4);
  this.bldLamps={};
  STAGES.forEach(k=>{const P=this.pl[k]=place(k);this.curStage=k;const B=this.makeBuilding(BLD_OF[k],p,wm,this.anims),g=B.g;this.bldLamps[k]=B.lamps;this.pl[k].top=B.top;
    const icon=ICON[k==='brand'?'brand':k==='ideas'?'ideas':k==='make'?'studio':k==='review'?'review':k==='publish'?'publish':k==='metrics'?'metrics':'report'];
    const tex=svgTex(`<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11.2" fill="#fff" stroke="${p.ink}" stroke-width="1.1"/><g fill="none" stroke="${p.ink}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" transform="translate(5 5) scale(.58)">${icon}</g></svg>`,128,128);
    const sg=B.sign,sign=new THREE.Mesh(new THREE.PlaneGeometry(sg.s,sg.s),new THREE.MeshBasicMaterial({map:tex,transparent:true}));sign.position.set(0,sg.y,sg.z);g.add(sign);
    g.scale.setScalar(BS);g.position.set(P.kx,0,P.kz);g.rotation.y=P.ry;g.userData.stage=k;world.add(g);this.kiosks.push(g);
    // pulse ring + soft disc (selected / needs you)
    const rg=new THREE.Group(),rm=new THREE.MeshBasicMaterial({color:SC[k],transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false}),dm=new THREE.MeshBasicMaterial({color:SC[k],transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false});
    const ringM=new THREE.Mesh(new THREE.RingGeometry(2.05,2.3,64),rm),discM=new THREE.Mesh(new THREE.CircleGeometry(2.05,48),dm);ringM.rotation.x=discM.rotation.x=-Math.PI/2;ringM.position.y=.05;discM.position.y=.045;rg.add(discM,ringM);rg.position.set(P.kx,0,P.kz);world.add(rg);this.rings[k]={g:rg,rm,dm,v:0,k:BS/1.3};
    const lab=sprite(labelTex(t('station.'+k)),6.4,1.2,P.kx,B.top*BS+.9,P.kz);world.add(lab);
    const ag=agent3(STAGE_ROLE[k],th,style);ag.home=new THREE.Vector3(P.hx,0,P.hz);ag.work=new THREE.Vector3(P.wx,0,P.wz);ag.guard=new THREE.Vector3(P.gx,0,P.gz);ag.g.scale.setScalar(AG);ag.g.position.copy(ag.home);ag.face=P.ry===0?0:(P.ry<0?-Math.PI/2:Math.PI/2);ag.g.rotation.y=Math.PI;world.add(ag.g);this.agents[STAGE_ROLE[k]]=ag;
    if(k==='report'){const ev=agent3('evolver',th,style);ev.home=new THREE.Vector3(P.hx-3.4,0,P.hz+.6);ev.work=ev.home.clone();ev.guard=ev.home.clone();ev.g.scale.setScalar(AG);ev.g.position.copy(ev.home);ev.g.rotation.y=Math.PI;world.add(ev.g);this.agents.evolver=ev}});
  // bin
  const bin=new THREE.Group();bin.add(hull(cy(.5,.4,.9,'#6b7280',0,.45,0,10),p.ink,1.07),cy(.55,.55,.1,'#4b5563',0,.95,0,10));bin.position.set(-W3.A-4.5,0,0);bin.scale.setScalar(2);bin.add(blob(.8,.2));world.add(bin);this.binLab=null;this.binG=bin;this.relabelBin();
  // barriers
  this.bars_={};[['review',GATE_S.review],['publish',GATE_S.publish]].forEach(([k,s])=>{const q=pt3(s),nx=-q.dz,nz=q.dx,B=W3.BW/2+.14,g=new THREE.Group();g.position.set(q.x-nx*B,0,q.z-nz*B);g.rotation.y=Math.atan2(-nz,nx);g.scale.setScalar(1.7);
    g.add(cy(.07,.08,1.25,'#555',0,.62,0,7));const light=sp(.14,'#e5483b',0,1.38,0,8);light.material=MB('#e5483b');g.add(light);
    const arm=new THREE.Group();arm.position.set(0,.95,0);const L=W3.BW+.32;for(let i=0;i<5;i++)arm.add(bx(L/5,.11,.11,i%2?'#fff':p.gate,L/10+i*L/5,0,0));g.add(arm);world.add(g);this.bars_[k]={arm,light,open:false,s}});
  // street lamps (they glow at night)
  const lampBulb=new THREE.MeshLambertMaterial({color:'#fff3cf',emissive:'#ffd98a',emissiveIntensity:0});this.glow.push(lampBulb);
  [[-11.2,-3.6],[-11.2,3.8],[11.6,-4.6],[11.6,4.2],[-6.2,6.9],[0,7.1],[6.4,6.9],[-15,-12],[0,-14],[15,-12]].forEach(([x,z])=>{x*=K3;z*=K3;const g=new THREE.Group();g.scale.setScalar(1.6);g.add(cy(.05,.07,3.0,'#4a4f57',0,1.5,0,6),bx(.5,.06,.06,'#4a4f57',.22,3.0,0));
    const bulb=new THREE.Mesh(new THREE.SphereGeometry(.17,10,8),lampBulb);bulb.position.set(.44,2.93,0);g.add(bulb);
    const halo=sprite(this.haloTex(),2.8,2.8,.44,2.93,0);halo.material.blending=THREE.AdditiveBlending;halo.visible=false;this.halos.push(halo);g.add(halo);g.position.set(x,0,z);world.add(g)});
  // decor
  const dg=new THREE.Group();dg.scale.setScalar(K3);world.add(dg);ex.decor(dg,th,this.anims);
  // followed-video marks: ring on the belt + a map pin above the item
  const tg=new THREE.Group(),tr=new THREE.Mesh(new THREE.RingGeometry(1.0,1.3,40),new THREE.MeshBasicMaterial({color:'#2f8fe8',transparent:true,opacity:.95,side:THREE.DoubleSide,depthWrite:false}));tr.rotation.x=-Math.PI/2;tr.position.y=.17;
  const pinS=sprite(this.pinTex(),1.5,1.9,0,2.9,0);pinS.center.set(.5,0);tg.add(tr,pinS);tg.visible=false;world.add(tg);this.trk={g:tg,ring:tr,pin:pinS};
  // shadows: every lit mesh casts and receives, except the big flat ground pieces
  world.traverse(o=>{if(o.isMesh&&o.material&&o.material.isMeshLambertMaterial){o.castShadow=true;o.receiveShadow=true}});flat.forEach(m=>{m.castShadow=false});
  this.buildWorld();this.applyTod();this.bars()},
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
  if(this.bgTex)this.bgTex.dispose();this.bgTex=gradTex(top,bot);this.scn.background=this.bgTex;this.scn.fog.color.set(bot);
  this.hemi.color.set(n?'#7f93f0':dk?'#8fa0e0':'#ffffff');this.hemi.groundColor.set(n?'#0a1022':(p.ground||ex.ground));this.hemi.intensity=(n?1.35:dk?1.5:2.0)*(W.hemi||1);
  this.sun.color.set(n?'#a9bcff':W.sunc||(dk?'#ffd9a8':'#ffffff'));this.sun.intensity=(n?1.0:dk?1.7:2.4)*(W.sun||1);if(this.groundMesh)this.groundMesh.material.color.set(W.ground?mixHex(ex.ground,W.ground,W.gk):ex.ground);
  this.glow.forEach(m=>{m.emissiveIntensity=n?1.1:0});this.halos.forEach(h=>{h.visible=n});
  this.world.children.forEach(o=>{if(o.isMesh&&o.material&&o.material.isMeshBasicMaterial&&o.position.y>=8&&o.geometry&&/Sphere|Circle/.test(o.geometry.type)){if(!o.userData.day)o.userData.day='#'+o.material.color.getHexString();if(th.id!=='dragons'&&th.id!=='cn')o.material.color.set(n?'#e6edff':o.userData.day)}});
  Object.values(this.agents).forEach(a=>{if(a.sprite)a.sprite.material.color.set(n?'#9fb0e0':'#ffffff')});this.applyWx();this.fit()},
 relabelBin(){if(!this.binG)return;if(this.binLab)this.binG.remove(this.binLab);const txt=t('bin')+(S.fails.length?' · '+S.fails.length:'');this.binLab=sprite(labelTex(txt,44),3.4,.64,0,2.0,0);this.binG.add(this.binLab)},
 size(){if(!this.R||!this.canvas)return;const slot=this.canvas.parentElement,w=Math.max(2,slot.clientWidth),h=Math.max(2,slot.clientHeight);this.R.setSize(w,h,false);this.cam.aspect=w/h;this.cam.updateProjectionMatrix();this.fit()},
 fit(){if(!this.canvas||!this.cam)return;const W=Math.max(2,this.canvas.clientWidth),H=Math.max(2,this.canvas.clientHeight),asp=W/H,port=asp<1,tan=Math.tan(this.cam.fov*Math.PI/360)*2,s=this.safe,sw=Math.max(120,W-s.l-s.r),sh=Math.max(120,H-s.t-s.b);
  const Wn=port?24:44,Hn=port?40:23.5,shf=port?Math.max(sh,H*.46):sh;this.D=Math.max(Wn*W/(sw*tan*asp),Hn*H/(shf*tan))*(port?1.0:1.02);this.port=port;if(this.scn&&this.scn.fog){this.scn.fog.near=this.D*1.25*(this.fogk||1);this.scn.fog.far=this.D*3.1*(this.fogk||1)}
  this.cam.setViewOffset(W,H,-(s.l-s.r)/2,-(s.t-s.b)/2,W,H);this.cam.updateProjectionMatrix()},
 setSafe(r){this.safe=r;this.fit()},
 project(v){const rect=this.canvas.getBoundingClientRect(),hr=this.host.getBoundingClientRect(),p=v.clone().project(this.cam);return{x:(p.x*.5+.5)*rect.width+(rect.left-hr.left),y:(-p.y*.5+.5)*rect.height+(rect.top-hr.top),vis:p.z<1}},
 anchor(k){if(k==='bin')return this.binG?new THREE.Vector3(this.binG.position.x,5.2,this.binG.position.z):null;const P=this.pl&&this.pl[k];return P?new THREE.Vector3(P.kx,P.top*BS+2.4,P.kz):null},
 nudge(d){const o=this.orb,b=o.to||{az:o.az,pol:o.pol,zoom:o.zoom,px:o.px,pz:o.pz};o.to=Object.assign({},b,d(b))},
 zoomBy(f){this.nudge(b=>({zoom:Math.max(.1,Math.min(2.4,b.zoom*f))}))},
 rotateBy(d){this.nudge(b=>({az:b.az+d}))},
 tiltBy(d){this.nudge(b=>({pol:Math.max(-.8,Math.min(.55,b.pol+d))}))},
 panBy(fwd,right){const a=(this.port?Math.PI/2:0)+this.orb.az;this.nudge(b=>({px:Math.max(-36,Math.min(36,b.px+Math.cos(a)*right-Math.sin(a)*fwd)),pz:Math.max(-36,Math.min(36,b.pz-Math.sin(a)*right-Math.cos(a)*fwd))}))},
 setFx(f){this.fx=f},
 bindPointer(){const c=this.canvas,o=this.orb;let down=null,pts=new Map(),last=null;
  const wpp=()=>0.7*this.D*o.zoom/Math.max(300,c.clientHeight);
  const pan=(dx,dy)=>{const a=(this.port?Math.PI/2:0)+o.az,k=wpp();o.px=Math.max(-36,Math.min(36,o.px-(Math.cos(a)*dx+Math.sin(a)*dy*1.25)*k));o.pz=Math.max(-36,Math.min(36,o.pz-(-Math.sin(a)*dx+Math.cos(a)*dy*1.25)*k))};
  c.addEventListener('contextmenu',e=>e.preventDefault());
  c.addEventListener('pointerdown',e=>{o.to=null;this.followRole=null;c.setPointerCapture(e.pointerId);pts.set(e.pointerId,{x:e.clientX,y:e.clientY});down={x:e.clientX,y:e.clientY,az:o.az,pol:o.pol,moved:0,pan:e.button===2||e.shiftKey||e.ctrlKey||e.metaKey};last={x:e.clientX,y:e.clientY};o.idle=0});
  c.addEventListener('pointermove',e=>{if(!pts.has(e.pointerId))return;const p=pts.get(e.pointerId);
   if(pts.size===2){const [a,b]=[...pts.values()],d0=Math.hypot(a.x-b.x,a.y-b.y),m0={x:(a.x+b.x)/2,y:(a.y+b.y)/2};p.x=e.clientX;p.y=e.clientY;const [a2,b2]=[...pts.values()],d1=Math.hypot(a2.x-b2.x,a2.y-b2.y),m1={x:(a2.x+b2.x)/2,y:(a2.y+b2.y)/2};o.zoom=Math.max(.1,Math.min(2.4,o.zoom*(d0/Math.max(1,d1))));pan(m1.x-m0.x,m1.y-m0.y);down&&(down.moved=99);return}
   p.x=e.clientX;p.y=e.clientY;if(!down)return;const dx=e.clientX-down.x,dy=e.clientY-down.y;down.moved=Math.max(down.moved,Math.hypot(dx,dy));
   if(down.pan){pan(e.clientX-last.x,e.clientY-last.y)}else{o.az=down.az-dx*.007;o.pol=Math.max(-.8,Math.min(.55,down.pol+dy*.0045))}last={x:e.clientX,y:e.clientY}});
  const up=e=>{pts.delete(e.pointerId);if(down&&down.moved<6&&pts.size===0&&e.button!==2){this.pick(e)}if(pts.size===0)down=null};c.addEventListener('pointerup',up);c.addEventListener('pointercancel',up);
  c.addEventListener('wheel',e=>{e.preventDefault();o.to=null;o.zoom=Math.max(.1,Math.min(2.4,o.zoom*Math.exp(e.deltaY*(e.ctrlKey?.01:.0015))))},{passive:false});
  c.addEventListener('dblclick',()=>this.resetView());
  this.keyH=e=>{if(!this.host||!this.host.matches(':hover')&&document.activeElement!==c)return;if(/INPUT|TEXTAREA|SELECT/.test((e.target||{}).tagName))return;const k=e.key.toLowerCase(),st=1.2*o.zoom*(e.shiftKey?2:1);
   const m={w:()=>this.panBy(st,0),arrowup:()=>this.panBy(st,0),s:()=>this.panBy(-st,0),arrowdown:()=>this.panBy(-st,0),a:()=>this.panBy(0,-st),arrowleft:()=>this.panBy(0,-st),d:()=>this.panBy(0,st),arrowright:()=>this.panBy(0,st),q:()=>this.rotateBy(-.25),e:()=>this.rotateBy(.25),'+':()=>this.zoomBy(1/1.2),'=':()=>this.zoomBy(1/1.2),'-':()=>this.zoomBy(1.2),r:()=>this.resetView(),f:()=>this.tiltBy(-.15),g:()=>this.tiltBy(.15)};
   if(m[k]&&!e.metaKey&&!e.ctrlKey&&!e.altKey){e.preventDefault();m[k]()}};window.addEventListener('keydown',this.keyH)},
 follow(r){this.followRole=r;if(r){this.orb.to={az:this.orb.az,pol:-.35,zoom:.32,px:this.orb.px,pz:this.orb.pz}}else this.orb.to={az:this.orb.az,pol:0,zoom:1,px:0,pz:0}},
 flyOver(){this.followRole=null;this.orb.to={az:this.orb.az+.9,pol:.5,zoom:1.7,px:0,pz:0}},
 resetView(){this.followRole=null;const o=this.orb,k=Math.round(o.az/(2*Math.PI))*2*Math.PI;o.az-=k;if(o.to)o.to.az-=k;o.to={az:0,pol:0,zoom:1,px:0,pz:0}},
 pick(e){const r=this.canvas.getBoundingClientRect(),m=new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-((e.clientY-r.top)/r.height)*2+1),rc=new THREE.Raycaster();rc.setFromCamera(m,this.cam);
  const ih=rc.intersectObjects([...this.items.values()],true);if(ih.length){let o=ih[0].object;while(o&&!o.userData.itemId)o=o.parent;if(o){S.track=o.userData.itemId;S.sel=null;Twin.update(true);return}}
  const ah=rc.intersectObjects(Object.values(this.agents).map(a=>a.g),true);if(ah.length){let o=ah[0].object;while(o&&!o.userData.role)o=o.parent;if(o){Chat.open(o.userData.role);return}}
  const hits=rc.intersectObjects(this.kiosks,true);if(hits.length){let o=hits[0].object;while(o&&!o.userData.stage)o=o.parent;if(o)Twin.select(o.userData.stage)}},
 /* --- sim bridge --- */
 place(c){const a=SIM.anchors['3d'],i=Math.min(7,Math.floor(c)),f=a[i]+(a[i+1]-a[i])*(c-i);return pt3(f*PATH3.L)},
 bars(){if(!this.scn)return;['review','publish'].forEach(k=>{const b=this.bars_[k];if(!b)return;const waiting=(k==='review'?S.queue:S.pubq).some(x=>x.sim);b.open=!waiting;b.light.material.color.set(b.open?'#2fbf71':'#e5483b')});
  ['gatekeeper','poster'].forEach((r,i)=>{const a=this.agents[r],k=i?'publish':'review';if(!a)return;const waiting=(k==='review'?S.queue:S.pubq).some(x=>x.sim);if(waiting&&!S.reduce)a.mode='guard';else if(a.mode==='guard')a.mode='home'})},
 bubble(ev){if(!ev.stage||this.hidden)return;const role=STAGE_ROLE[ev.stage],a=this.agents[role];
  if(a&&!S.reduce){if(ev.kind==='gate.review'||ev.kind==='gate.publish'){a.mode='guard'}else{a.mode='work';a.t=0;a.workDur=ev.kind==='make.started'?1.9:1.2}}
  if(role==='reflector'&&this.agents.evolver&&!S.reduce&&ev.kind==='hints.generated'){const e=this.agents.evolver;e.mode='bounce';e.t=0}
  const old=this.bubs.filter(b=>!b.dead);while(old.length>=2){const b=old.shift();b.el.remove();b.dead=true}
  const el=document.createElement('div');el.className='bubble';el.style.setProperty('--bub',SC[ev.stage]);el.innerHTML=`<b>${esc(charName(role))}</b>${esc(phrase(ev))}`;this.host.appendChild(el);
  const b={el,role,born:performance.now(),dead:false,slot:old.length};this.bubs.push(b);const life=S.keep?1e9:S.reduce?5200:3900;b.life=life},
 draw(dt){if(!this.R||!this.scn)return;this.clock+=dt;const T=this.clock;
  // belt, items
  this.beltTex.offset.x-=dt*(S.loop==='running'?SPEED/PX3:0);
  const live=SIM.items;for(const [id,g] of this.items)if(!live.some(i=>i.id===id)){this.world.remove(g);this.items.delete(id)}
  for(const it of live){let g=this.items.get(it.id);if(!g){g=this.mkItem(it);g.userData.itemId=it.id;this.world.add(g);this.items.set(it.id,g)}
    const q=this.place(Math.min(it.c,7.999));g.position.set(q.x,.95+Math.sin(T*3+it.n)*.02,q.z);g.rotation.y=Math.atan2(q.dx,q.dz)+Math.PI/2;
    const col=it.cracked?'#7a1f1f':STATECOL[it.state]||'#999';g.userData.body.material.color.set(col);g.userData.body.material.emissive.set(col);g.userData.body.material.emissiveIntensity=S.tod==='night'?.4:0;g.userData.gold.visible=!!(it.gold&&['published','measured','archived'].includes(it.state));g.userData.crack.visible=!!it.cracked;
    if(g.userData.gold.visible)g.userData.gold.material.opacity=.45+Math.sin(T*4)*.25;
    const o=it.dead?Math.max(0,1-it.fade):1;g.traverse(m=>{if(m.material&&m.material!==g.userData.gold.material){m.material.transparent=o<1;m.material.opacity=o}})}
  // fx: pulse rings under stations, the followed video's ring, pin and ribbon
  const fx=this.fx||{};
  for(const k in this.rings){const R=this.rings[k],need=fx.need&&fx.need[k],tgt=need?.9:fx.sel===k?.75:0;R.v+=(tgt-R.v)*Math.min(1,dt*8);R.rm.color.set(need?'#e0a21a':SC[k]);R.dm.color.copy(R.rm.color);R.rm.opacity=R.v*(need&&!S.reduce?.62+.33*Math.sin(T*4):1);R.dm.opacity=R.v*.17;R.g.scale.setScalar(R.k*(S.reduce?1:1+Math.sin(T*3.2)*.04))}
  const ti=fx.track&&SIM.items.find(i=>i.id===fx.track&&!i.dead),tk=this.trk;
  if(tk){tk.g.visible=!!ti;this.trail.visible=!!ti;if(ti){const cc=Math.min(ti.c,7.999),q=this.place(cc),a=SIM.anchors['3d'],ii=Math.floor(cc),f=a[ii]+(a[ii+1]-a[ii])*(cc-ii);tk.g.position.set(q.x,0,q.z);const sc=1+Math.sin(T*4)*.07;tk.ring.scale.set(sc,sc,sc);tk.ring.material.opacity=.7+Math.sin(T*4)*.25;tk.pin.position.y=2.9+Math.sin(T*3)*.12;this.trail.geometry.setDrawRange(0,Math.max(0,Math.floor(f*this.N))*6)}this.dashTex.offset.x-=dt*.9}
  // sub-step lamps on every building
  if(this.bldLamps){const it0=fx.track&&SIM.items.find(i=>i.id===fx.track&&!i.dead);for(const k of STAGES){const st=Twin.subs(k,it0),ls=this.bldLamps[k];if(!ls)continue;ls.forEach((l,i)=>{const s0=st[i]||'todo',m=l.material;if(s0==='done'){m.color.set(SC[k]);m.emissive.set(SC[k]);m.emissiveIntensity=.8}else if(s0==='cur'||s0==='wait'){const a=S.reduce?1:.6+.4*Math.sin(T*6);m.color.set('#ffc247');m.emissive.set('#ffb21f');m.emissiveIntensity=a*(s0==='wait'?1.1:1)}else{m.color.set('#8c97a4');m.emissive.set('#000000');m.emissiveIntensity=0}})}}
  // agents
  const dtt=Math.min(dt,.05);this.drawWorld(T,dtt);for(const r in this.agents)this.stepAgent(this.agents[r],dtt,T);
  // decor
  this.anims.forEach(fn=>fn(T,dtt));
  // camera
  const o=this.orb;o.idle+=dt;if(o.to){const k=Math.min(1,dt*7);['az','pol','zoom','px','pz'].forEach(a=>{o[a]+=(o.to[a]-o[a])*k});if(['az','pol','zoom','px','pz'].every(a=>Math.abs(o.to[a]-o[a])<.002)){Object.assign(o,o.to);o.to=null}}const sway=S.reduce?0:Math.sin(T*.25)*.05,az=(this.port?Math.PI/2:0)+o.az+sway,polB=Math.max(.12,Math.min(1.5,.95+o.pol));
  // an explicitly selected station pulls the camera a little closer, then it eases back
  const bx0=this.port?1.0:1.8,bz0=this.port?-3.2:-3.6,pk=this.fx&&this.fx.pin&&this.pl[this.fx.pin],fo=this.foc||(this.foc={x:0,z:0,k:1}),fe=S.reduce?1:Math.min(1,dt*3);
  let gx=pk?(pk.kx-bx0)*.4:0,gz=pk?(pk.kz-bz0)*.4:0,gk=pk?.7:1;
  if(!pk&&this.port&&!this.followRole&&o.idle>3){const tid=this.fx&&this.fx.track,ti2=tid&&SIM.items.find(i=>i.id===tid&&!i.dead);if(ti2){const q2=this.place(Math.min(ti2.c,7.999));gx=(q2.x-bx0)*.9;gz=(q2.z-bz0)*.9;gk=.5}}
  fo.x+=(gx-fo.x)*fe;fo.z+=(gz-fo.z)*fe;fo.k+=(gk-fo.k)*fe;
  if(this.followRole&&this.agents[this.followRole]){const a=this.agents[this.followRole].g.position,kf=Math.min(1,dt*3.5);o.px+=((a.x-bx0-fo.x)-o.px)*kf;o.pz+=((a.z-bz0-fo.z)-o.pz)*kf}
  const D=this.D*o.zoom*fo.k,tx=bx0+fo.x+o.px,ty=0,tz=bz0+fo.z+o.pz;this.cam.position.set(tx+Math.sin(az)*Math.cos(polB)*D*1.0,ty+Math.sin(polB)*D,tz+Math.cos(az)*Math.cos(polB)*D);this.cam.lookAt(tx,ty+1.0,tz);
  this.R.render(this.scn,this.cam);
  // bubbles follow agents
  const rect=this.canvas.getBoundingClientRect(),hr=this.host.getBoundingClientRect(),now=performance.now(),v=new THREE.Vector3();
  this.bubs=this.bubs.filter(b=>{if(b.dead){return false}const age=now-b.born;if(age>b.life+500){b.el.remove();return false}if(age>b.life)b.el.classList.add('out');
    const a=this.agents[b.role];if(!a)return true;v.copy(a.g.position);v.y+=2.3;v.project(this.cam);const x=(v.x*.5+.5)*rect.width+(rect.left-hr.left),y=(-v.y*.5+.5)*rect.height+(rect.top-hr.top)-(b.slot?64:0);
    b.el.style.left=Math.max(70,Math.min(hr.width-70,x))+'px';b.el.style.top=Math.max(this.safe.t+(b.el.offsetHeight||56)+8,y)+'px';return true})},
 mkItem(it){const g=new THREE.Group(),body=hull(bx(.56,.78,.3,'#999',0,0,0),'#0f2233',1.08),poster=new THREE.Mesh(new THREE.PlaneGeometry(.42,.54),new THREE.MeshBasicMaterial({map:this.posterTex(it&&it.n)}));poster.position.set(0,.06,.153);g.add(body,poster,sp(.04,'#0f2233',-.12,-.31,.16,6),sp(.04,'#0f2233',.12,-.31,.16,6),new THREE.Mesh(new THREE.SphereGeometry(.9,8,6),new THREE.MeshBasicMaterial({visible:false})));
  const gold=sprite(ctex(64,64,(c,w,h)=>{const gr=c.createRadialGradient(w/2,h/2,2,w/2,h/2,w/2);gr.addColorStop(0,'rgba(255,226,122,.95)');gr.addColorStop(1,'rgba(255,226,122,0)');c.fillStyle=gr;c.fillRect(0,0,w,h)}),1.9,1.9,0,0,0);gold.material.opacity=.6;gold.visible=false;g.add(gold);
  const crack=bx(.04,.6,.32,'#fff',0,0,0);crack.rotation.z=.5;crack.visible=false;g.add(crack);g.userData={body,gold,crack};g.scale.setScalar(1.95);g.add(blob(.4,.2));g.children[g.children.length-1].position.y=-.48;return g},
 stepAgent(a,dt,T){const L=a.limbs;let target=a.mode==='work'||a.mode==='bounce'?a.work:a.mode==='guard'?a.guard:a.home;if(S.reduce){a.g.position.copy(target);target=a.g.position}
  const d=Math.hypot(target.x-a.g.position.x,target.z-a.g.position.z),walking=d>.06;
  if(walking){const sp=3.6*dt,k=Math.min(1,sp/d);a.g.position.x+=(target.x-a.g.position.x)*k;a.g.position.z+=(target.z-a.g.position.z)*k;const ang=Math.atan2(target.x-a.g.position.x,target.z-a.g.position.z);let da=ang-a.g.rotation.y;da=Math.atan2(Math.sin(da),Math.cos(da));a.g.rotation.y+=da*Math.min(1,dt*10);a.ph+=dt*9}
  else{let da=this.faceTo(a)-a.g.rotation.y;da=Math.atan2(Math.sin(da),Math.cos(da));a.g.rotation.y+=da*Math.min(1,dt*6);
   if(a.mode==='work'||a.mode==='bounce'){a.t+=dt;if(a.t>a.workDur){a.mode=(a.mode==='bounce')?'home':'home';a.t=0}}}
  if(a.sprite){a.sprite.position.y=(a.sy||1.2)+(walking?Math.abs(Math.sin(a.ph))*.14:Math.sin(T*2+a.ph)*.02);a.sprite.material.rotation=walking?Math.sin(a.ph)*.07:0;return}
  const sw=walking?Math.sin(a.ph):0,work=!walking&&(a.mode==='work'||a.mode==='bounce');
  L.legL.rotation.x=sw*.75;L.legR.rotation.x=-sw*.75;L.armL.rotation.x=-sw*.6;L.armR.rotation.x=work?-1.5+Math.sin(T*10)*.55:sw*.6;
  if(a.mode==='guard'&&!walking){L.armR.rotation.x=-.2;L.armL.rotation.x=0}
  L.body.position.y=walking?Math.abs(Math.sin(a.ph))*.07:(work?Math.abs(Math.sin(T*10))*.04:Math.sin(T*2+a.ph)*.012);
  if(a.bulb){a.bulb.scale.setScalar(1+Math.sin(T*3)*.08)}if(a.paddle){a.paddle.forEach(m=>m.visible=true)}},
 faceTo(a){const P=this.pl[Object.keys(STAGE_ROLE).find(k=>STAGE_ROLE[k]===a.role)||'report'];if(!P)return Math.PI;const dx=P.q.x-a.g.position.x,dz=P.q.z-a.g.position.z;return Math.atan2(dx,dz)}
};
