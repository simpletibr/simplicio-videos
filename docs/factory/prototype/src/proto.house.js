/* ===== Houses as cutaways: no front wall, so the camera sees the rooms from the front like a 2D side view while
   the structure is 3D. One house per stage, one room per sub-step. The belt runs along the front of every house. ===== */
const BLD_OF={brand:'house',ideas:'lab',make:'factory',review:'garage',publish:'market',metrics:'observatory',report:'barn'};
const SUBS={brand:4,ideas:4,make:5,review:3,publish:4,metrics:3,report:3};
const HOUSE_SIDE={brand:'top',ideas:'top',make:'top',review:'right',publish:'bottom',metrics:'bottom',report:'left'};
const RW=3.6,HD=5.6;   // room width, house depth

Object.assign(SceneThree,{
  /* a small canvas texture: a screen, a board, a poster */
  miniTex(w,h,fn){return ctex(w,h,fn)},
  makeHouse(k,p,wm,anims){
    p=Object.assign({},p,{roof:mixHex(p.roof,SC[k],.5),wall:mixHex(p.wall,SC[k],.22),accent:mixHex(p.accent,SC[k],.35)});   // each house leans on its stage color
    const n=SUBS[k],W=n*RW+1.0,Ht=k==='metrics'?5.2:4.6,type=BLD_OF[k],g=new THREE.Group(),ink=p.ink,gl=this.glow,
      H=(m,kk)=>hull(m,ink,kk||1.03),wall=p.wall,floorC=shade(wall,-.22);
    const rooms=[];for(let i=0;i<n;i++)rooms.push({x:-W/2+.5+RW*(i+.5)});
    // shell: floor, back wall, side walls, thin room dividers; the front is open on purpose
    g.add(H(bx(W+.6,.34,HD+.5,floorC,0,.17,.0)),bx(W,Ht,.3,wall,0,Ht/2+.34,-HD/2+.15),bx(.3,Ht,HD,shade(wall,-.06),-W/2+.15,Ht/2+.34,0),bx(.3,Ht,HD,shade(wall,-.06),W/2-.15,Ht/2+.34,0));
    for(let i=1;i<n;i++)g.add(bx(.16,2.0,HD*.72,shade(wall,-.1),-W/2+.5+RW*i,1.34,-HD*.14));
    const rugs=[];rooms.forEach(r=>{const rg=bx(RW-.35,.05,HD-.9,shade(p.accent,.15),r.x,.37,.05);rg.userData.base=shade(p.accent,.15);g.add(rg);rugs.push(rg)});
    // roof by building type
    const roofY=Ht+.34;let top=Ht+.34;
    const ridge=(w,d,c,y,sl)=>{[-1,1].forEach(s=>{const r=H(bx(w,.22,d/2+.9,c,0,y+Math.abs(Math.sin(sl))*d/4,s*(d/4+.1)),1.03);r.rotation.x=-s*sl;g.add(r)});g.add(bx(w,.22,.35,shade(c,-.15),0,y+Math.sin(sl)*d/2*.5+.3,0))};
    const smoke=(x,y,z,cnt,sc)=>{const puffs=[];for(let i=0;i<cnt;i++){const m=new THREE.Mesh(new THREE.SphereGeometry(.34,8,6),new THREE.MeshBasicMaterial({color:'#f2f4f7',transparent:true,opacity:0,depthWrite:false}));m.position.set(x,y,z);g.add(m);puffs.push({m,ph:i/cnt})}
      anims.push(t=>{if(S.reduce)return;puffs.forEach(q=>{const u=((t*.25+q.ph)%1);q.m.position.y=y+u*2.6*(sc||1);q.m.position.x=x+u*.7;q.m.scale.setScalar(.5+u*1.6);q.m.material.opacity=.55*(1-u)*Math.min(1,u*6)})})};
    if(type==='house'){ridge(W+1.6,HD,p.roof,roofY+.2,.5);g.add(bx(.6,1.1,.6,shade(p.roof,-.25),W/2-1.4,roofY+1.6,-.8));smoke(W/2-1.4,roofY+2.3,-.8,3,1.2);top=roofY+2.6}
    else if(type==='lab'){g.add(bx(W+.8,.3,HD+.9,p.roof,0,roofY+.15,.1),bx(W+.8,.4,.14,p.accent,0,roofY+.4,HD/2+.5));
      g.add(cy(.7,.2,.5,'#d9dde3',W/2-2,roofY+.6,-.6,12),cy(.04,.04,1.2,ink,W/2-2,roofY+1.2,-.6,6));const b=sp(.4,'#fff1b8',-W/2+2,roofY+.8,-.6,12);b.material=new THREE.MeshLambertMaterial({color:'#fff1b8',emissive:'#ffd24a',emissiveIntensity:0});gl.push(b.material);g.add(b,cy(.1,.1,.6,ink,-W/2+2,roofY+.4,-.6,6));top=roofY+1.5}
    else if(type==='factory'){const shp=new THREE.Shape();shp.moveTo(-.9,0);shp.lineTo(-.9,1.5);shp.lineTo(.9,0);shp.closePath();const cnt=Math.round(W/2.4);
      for(let i=0;i<cnt;i++){const w=new THREE.Mesh(new THREE.ExtrudeGeometry(shp,{depth:HD+.8,bevelEnabled:false}),LM(p.roof));w.position.set(-W/2+1.2+i*(W-2.4)/(cnt-1||1),roofY,-HD/2-.4);g.add(w)}
      [[-W/2+1.2,-1.4],[-W/2+3.6,-1.4]].forEach(([x,z])=>{g.add(cy(.42,.5,3,'#8e5a43',x,roofY+1.5,z,12),cy(.44,.44,.28,p.accent,x,roofY+3,z,12));smoke(x,roofY+3.3,z,3,1.5)});top=roofY+3.5}
    else if(type==='garage'){g.add(bx(W+.8,.3,HD+.9,shade(p.roof,-.05),0,roofY+.15,.1),bx(W+.8,.32,.14,'#ffd23f',0,roofY+.1,HD/2+.55));
      for(let i=0;i<Math.floor((W+.8)/.7);i++)g.add(bx(.35,.33,.15,i%2?ink:'#ffd23f',-W/2-.1+i*.7+.2,roofY+.1,HD/2+.56));
      g.add(cy(.06,.06,2.2,ink,W/2-.7,roofY+1.3,.4,6),bx(.9,.6,.05,'#ffffff',W/2-.25,roofY+2.1,.4),bx(.45,.3,.06,ink,W/2-.47,roofY+2.25,.4),bx(.45,.3,.06,ink,W/2-.03,roofY+1.95,.4));
      const lamp=sp(.28,'#ff7a6d',0,roofY+.7,0,10);lamp.material=new THREE.MeshLambertMaterial({color:'#ff7a6d',emissive:'#ff3b2d',emissiveIntensity:.6});g.add(lamp);top=roofY+2.6}
    else if(type==='market'){const cols=[[p.roof,'#ffffff'],['#2f9a5a','#ffd23f'],['#e85d2a','#ffffff'],[p.accent,'#ffffff']];
      for(let i=0;i<n;i++){const x=rooms[i].x,c=cols[i%4],gp=new THREE.Group();for(let j=0;j<6;j++)gp.add(bx(RW/6-.01,.14,HD*.55,j%2?c[1]:c[0],-RW/2+RW/6*(j+.5)+.0,0,0));gp.position.set(x,roofY-.3,HD*.18);gp.rotation.x=-.32;g.add(gp)}
      g.add(cy(.07,.07,3.4,ink,W/2-.5,Ht*.5+.5,HD/2-.4,6),bx(1.1,.7,.06,'#ffd23f',W/2+.1,Ht+1.8,HD/2-.4));top=Ht+2.6}
    else if(type==='observatory'){g.add(bx(W+.6,.3,HD+.6,shade(wall,.05),0,roofY+.15,0));
      const dome=new THREE.Mesh(new THREE.SphereGeometry(RW*.95,22,12,0,Math.PI*2,0,Math.PI/2),LM(p.roof));dome.position.set(0,roofY+.3,-.3);g.add(H(dome,1.02));
      g.add(bx(.55,RW*.9,.9,shade(ink,.25),0,roofY+RW*.5,RW*.85-.8),cy(.2,.26,2.4,'#d9dde3',.6,roofY+RW*.95,RW*.45,10));g.children[g.children.length-1].rotation.x=-.9;top=roofY+RW+.8}
    else{ // barn: gambrel roof
      [-1,1].forEach(s=>{const r=H(bx(W+1.0,.22,HD*.42,shade(p.roof,-.1),0,roofY+.7,s*HD*.2),1.03);r.rotation.x=-s*.5;g.add(r);const r2=H(bx(W+1.0,.22,HD*.28,shade(p.roof,-.18),0,roofY-.1,s*HD*.42),1.03);r2.rotation.x=-s*.18;g.add(r2)});
      const vane=cn(.18,.7,'#ffd23f',W/2-1,roofY+2.1,0,5);vane.rotation.z=-Math.PI/2;g.add(cy(.04,.04,1.3,ink,W/2-1,roofY+1.5,0,5),vane);anims.push(t=>{vane.rotation.y=S.reduce?0:Math.sin(t*.9)*1.2});top=roofY+2.4}
    // back-wall windows, room plaques and lamps
    const lamps=[];
    rooms.forEach((r,i)=>{const w=new THREE.Mesh(new THREE.BoxGeometry(RW-.25,.95,.06),wm);w.position.set(r.x,Ht-.5,-HD/2+.34);g.add(w);
      const pl=sprite(labelTex(t('sub.'+k+'.'+i),62),RW-.1,.92,r.x,Ht-.5,-HD/2+.5);pl.material.depthTest=false;pl.renderOrder=5;g.add(pl);
      const m=new THREE.MeshLambertMaterial({color:'#8c97a4',emissive:'#000000',emissiveIntensity:1}),l=new THREE.Mesh(new THREE.SphereGeometry(.17,10,8),m);l.position.set(r.x+1.2,Ht-1.3,-HD/2+.5);g.add(l);lamps.push(l);
      this.roomKit(k,i,g,r.x,p,anims,wm)});
    // roof-top row of lamps for the view from above
    const roofLamps=[];
    for(let i=0;i<n;i++){const m=new THREE.MeshLambertMaterial({color:'#8c97a4',emissive:'#000000',emissiveIntensity:1}),l=new THREE.Mesh(new THREE.SphereGeometry(.3,10,8),m);l.position.set(rooms[i].x,Ht+.9,HD/2+.15);g.add(bx(.5,.35,.5,shade(ink,.1),rooms[i].x,Ht+.55,HD/2+.15),l);roofLamps.push(l)}
    const nl=new THREE.PointLight('#ffd9a0',0,18,1.6);nl.position.set(0,Ht*.6,HD/2-.6);g.add(nl);this.nightLights.push(nl);
    return{g,W,Ht,top,rooms,lamps,roofLamps,rugs}},

  /* props: each sub-step gets its own little corner */
  roomKit(k,i,g,cx,p,anims,wm){const ink=p.ink,Z=-1.0,wd='#b98552',met='#c9ced6',scr=(fn)=>new THREE.Mesh(new THREE.PlaneGeometry(1.1,.7),new THREE.MeshBasicMaterial({map:this.miniTex(128,80,fn)}));
    const desk=(x,z,c)=>{g.add(bx(1.7,.14,.9,c||wd,x,1.3,z),bx(.12,1.0,.12,shade(c||wd,-.2),x-.7,.8,z-.3),bx(.12,1.0,.12,shade(c||wd,-.2),x+.7,.8,z-.3),bx(.12,1.0,.12,shade(c||wd,-.2),x-.7,.8,z+.3),bx(.12,1.0,.12,shade(c||wd,-.2),x+.7,.8,z+.3))};
    const screen=(x,y,z,fn)=>{const s=scr(fn);s.position.set(x,y,z);g.add(bx(1.25,.85,.1,'#243242',x,y,z-.07),s)};
    const board=(x,y,z,w,h,fn)=>{const s=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshBasicMaterial({map:this.miniTex(160,100,fn)}));s.position.set(x,y,z);g.add(bx(w+.16,h+.16,.08,'#f4f1e6',x,y,z-.05),s)};
    const post=(c,x,y,z,r)=>{const m=bx(.34,.34,.02,c,x,y,z);m.rotation.z=r||0;g.add(m)};
    const key=k+i,bY=0.36,bz=-HD/2+.5;
    if(key==='brand0'){desk(cx,Z,wd);screen(cx,2.15,Z-.25,(c,w,h)=>{c.fillStyle='#fff';c.fillRect(0,0,w,h);c.fillStyle=p.roof;c.fillRect(0,0,w,14);c.fillStyle='#d6dde6';for(let y=24;y<h-6;y+=14)c.fillRect(8,y,w*(.5+((y*7)%40)/100),7);c.fillStyle=p.accent;c.fillRect(w-40,24,30,30)})}
    else if(key==='brand1'){board(cx,2.3,bz+.15,2.6,1.5,(c,w,h)=>{c.fillStyle='#d9a56e';c.fillRect(0,0,w,h);['#ffe27a','#ff9bb3','#9fe3b6','#9ed0ff','#ffd23f'].forEach((q,j)=>{c.fillStyle=q;c.fillRect(14+(j%3)*48,12+Math.floor(j/3)*44,38,34)});c.strokeStyle='#c0392b';c.lineWidth=2;c.beginPath();c.moveTo(30,30);c.lineTo(78,28);c.lineTo(126,60);c.stroke()});desk(cx,Z+.3,'#a9764a')}
    else if(key==='brand2'){g.add(bx(2.4,2.2,.5,'#8a5a2b',cx,1.5,bz+.2));for(let r=0;r<3;r++)for(let c=0;c<5;c++)g.add(bx(.3,.5,.34,['#e5483b','#2a62c9','#f5c542','#2f9a5a','#8e44ad'][(r+c)%5],cx-.9+c*.45,.95+r*.7,bz+.5));g.add(cy(.28,.28,.4,'#ffd23f',cx+.3,.56,Z+.9,12),bx(.4,.2,.4,'#c0392b',cx-.6,.46,Z+.9))}
    else if(key==='brand3'){g.add(bx(1.5,2.3,.9,'#aeb6c2',cx,1.5,bz+.5));for(let d=0;d<3;d++)g.add(bx(1.3,.6,.05,shade('#aeb6c2',.15),cx,.95+d*.72,bz+1.0),bx(.4,.06,.07,ink,cx,1.0+d*.72,bz+1.06));const d=cy(.5,.5,.1,'#58b4ff',cx+1.2,1.0,Z+.8,16);d.material=new THREE.MeshLambertMaterial({color:'#9fd6ff',emissive:'#58b4ff',emissiveIntensity:.9});g.add(d)}
    else if(key==='ideas0'){board(cx,2.35,bz+.15,2.8,1.6,(c,w,h)=>{c.fillStyle='#fff';c.fillRect(0,0,w,h);c.strokeStyle='#2a62c9';c.lineWidth=3;c.beginPath();c.moveTo(12,70);c.quadraticCurveTo(50,10,90,60);c.quadraticCurveTo(110,85,146,30);c.stroke();c.fillStyle='#ffd23f';c.beginPath();c.arc(120,30,12,0,7);c.fill()});const b=sp(.34,'#ffe27a',cx,3.6,Z+.4,10);b.material=new THREE.MeshLambertMaterial({color:'#fff1b8',emissive:'#ffd24a',emissiveIntensity:.8});g.add(b);this.glow.push(b.material);desk(cx,Z+.7,'#d9c9a3')}
    else if(key==='ideas1'){g.add(bx(.22,2.6,.4,'#2f9a5a',cx-1.1,1.7,Z),bx(.22,2.6,.4,'#2f9a5a',cx+1.1,1.7,Z),bx(2.4,.3,.4,'#2f9a5a',cx,3.0,Z));const ck=bx(.8,.8,.06,'#e1f5e8',cx,1.75,Z+.2);g.add(ck,bx(.14,.4,.07,'#17865a',cx-.12,1.7,Z+.24),bx(.14,.7,.07,'#17865a',cx+.14,1.82,Z+.24))}
    else if(key==='ideas2'){[[-.9,1.0,'#c0c6d0'],[0,1.7,'#f5c542'],[.9,.7,'#cd7f32']].forEach(([x,h,c],j)=>{g.add(bx(.8,h,.8,c,cx+x,.36+h/2,Z+.4),bx(.5,.5,.06,'#fff',cx+x,.36+h*.6,Z+.82));const st=cn(.2,.4,'#ffd23f',cx+x,.5+h+.2,Z+.4,5);g.add(st)})}
    else if(key==='ideas3'){g.add(cy(.9,1.0,.9,'#8e99a8',cx,.8,Z+.4,16),cy(.55,.55,.28,'#e5483b',cx,1.4,Z+.4,16));const r=new THREE.Mesh(new THREE.TorusGeometry(.8,.05,6,24),new THREE.MeshBasicMaterial({color:'#ffd23f'}));r.rotation.x=Math.PI/2;r.position.set(cx,1.0,Z+.4);g.add(r);anims.push(t=>{r.scale.setScalar(1+Math.sin(t*3)*.05)})}
    else if(key==='make0'){desk(cx,Z+.2,wd);g.add(bx(.9,.06,.7,'#fff',cx-.2,1.4,Z+.2),bx(.5,.3,.5,'#4a4f57',cx+.5,1.52,Z+.2),bx(.3,.04,.3,'#fff',cx+.5,1.74,Z+.1));screen(cx,2.3,bz+.2,(c,w,h)=>{c.fillStyle='#10243a';c.fillRect(0,0,w,h);c.fillStyle='#9fd6ff';for(let y=12;y<h-6;y+=12)c.fillRect(10,y,30+((y*13)%70),5)})}
    else if(key==='make1'){g.add(bx(2.2,2.4,.14,'#3a4656',cx,1.6,Z-.2),bx(.14,2.4,1.5,'#3a4656',cx-1.1,1.6,Z+.5),bx(.14,2.4,1.5,'#3a4656',cx+1.1,1.6,Z+.5),bx(2.2,.14,1.5,'#3a4656',cx,2.85,Z+.5));g.add(cy(.05,.05,1.1,'#222',cx,1.9,Z+.6,6),sp(.22,'#2a2f38',cx,2.55,Z+.6,10));for(let j=0;j<3;j++){const w=new THREE.Mesh(new THREE.TorusGeometry(.35+j*.18,.03,6,20),new THREE.MeshBasicMaterial({color:'#7cc8ff',transparent:true,opacity:.6}));w.position.set(cx+1.5,1.9,Z+.6);w.rotation.y=Math.PI/2;g.add(w);anims.push(t=>{const u=((t*.8+j*.33)%1);w.scale.setScalar(.6+u);w.material.opacity=.7*(1-u)})}}
    else if(key==='make2'){g.add(bx(2.2,.16,1.3,'#d9c9a3',cx,1.2,Z+.4),bx(.14,.9,.14,'#8a5a2b',cx-.9,.75,Z+.1),bx(.14,.9,.14,'#8a5a2b',cx+.9,.75,Z+.1));[0,1,2].forEach(j=>g.add(bx(.55,.4,.04,['#ffb3c8','#9ed0ff','#ffe27a'][j],cx-.65+j*.65,1.5,Z+.45)));board(cx,2.3,bz+.15,2.4,1.4,(c,w,h)=>{c.fillStyle='#10243a';c.fillRect(0,0,w,h);[0,1,2].forEach(j=>{c.fillStyle=['#ffb3c8','#9ed0ff','#ffe27a'][j];c.fillRect(8+j*50,20,44,60)})})}
    else if(key==='make3'){g.add(bx(2.2,2.2,1.3,'#6b7787',cx,1.45,Z+.1));const bar=bx(1.6,.18,.05,'#58e08a',cx-.8,1.85,Z+.78);bar.material=new THREE.MeshBasicMaterial({color:'#58e08a'});bar.geometry.translate(.8,0,0);g.add(bx(1.7,.28,.04,'#243242',cx,1.85,Z+.76),bar);const gear=cy(.5,.5,.1,'#ffb86b',cx+.5,1.0,Z+.78,12);gear.rotation.x=Math.PI/2;g.add(gear);const lt=sp(.14,'#ff5a4d',cx-.9,2.4,Z+.78,8);lt.material=new THREE.MeshBasicMaterial({color:'#ff5a4d'});g.add(lt);anims.push(t=>{bar.scale.x=.15+((t*.2)%1)*.85;gear.rotation.z=t*1.4;lt.visible=((t*2)%1)>.4})}
    else if(key==='make4'){screen(cx,2.0,Z,(c,w,h)=>{c.fillStyle='#10243a';c.fillRect(0,0,w,h);c.strokeStyle='#58e08a';c.lineWidth=7;c.beginPath();c.moveTo(40,44);c.lineTo(58,62);c.lineTo(92,22);c.stroke()});g.add(cy(.1,.1,1.4,'#444',cx,1.0,Z-.1,6),bx(.9,.1,.6,'#444',cx,.4,Z-.1))}
    else if(key==='review0'){board(cx,2.2,bz+.15,2.6,1.7,(c,w,h)=>{c.fillStyle='#fff';c.fillRect(0,0,w,h);[0,1,2].forEach(j=>{c.strokeStyle='#2a62c9';c.lineWidth=3;c.strokeRect(14,14+j*30,18,18);c.fillStyle='#9aa8b6';c.fillRect(44,20+j*30,90,7);if(j===0){c.strokeStyle='#17865a';c.beginPath();c.moveTo(17,24);c.lineTo(23,30);c.lineTo(30,17);c.stroke()}})});desk(cx,Z+.5,'#9aa2ad')}
    else if(key==='review1'){g.add(bx(.22,2.4,.5,'#4a4f57',cx-1.0,1.55,Z+.4),bx(.22,2.4,.5,'#4a4f57',cx+1.0,1.55,Z+.4),bx(2.2,.3,.5,'#4a4f57',cx,2.85,Z+.4));const ls=bx(1.8,.05,.05,'#ff3b2d',cx,2.0,Z+.4);ls.material=new THREE.MeshBasicMaterial({color:'#ff3b2d'});g.add(ls);anims.push(t=>{ls.position.y=1.0+((t*.7)%1)*1.6});g.add(bx(.5,.28,.5,'#243242',cx+.4,.85,Z+.4))}
    else if(key==='review2'){desk(cx,Z+.2,'#9aa2ad');const lv=(x,c)=>{g.add(cy(.05,.05,.7,'#333',x,1.7,Z+.2,6),sp(.14,c,x,2.12,Z+.2,8))};lv(cx-.4,'#e5483b');lv(cx+.4,'#17a35a');g.add(bx(1.0,.14,.5,'#10243a',cx,1.42,Z+.2))}
    else if(key==='publish0'){desk(cx,Z+.3,'#e8dcc0');const pp=cn(.4,1.1,'#ffffff',cx,1.8,Z+.3,3);pp.rotation.z=-Math.PI/2;g.add(pp);anims.push(t=>{pp.position.y=1.8+Math.sin(t*2)*.08})}
    else if(key==='publish1'){[0,1,2].forEach(j=>{const c=['#e5483b','#2a62c9','#17a35a'][j];g.add(bx(.6,.9,.55,c,cx-.8+j*.8,1.2,Z+.3),bx(.45,.06,.4,'#10243a',cx-.8+j*.8,1.2,Z+.6),bx(.1,.35,.04,'#fff',cx-.8+j*.8,1.62,Z+.6),cy(.04,.04,.7,'#6b7280',cx-.8+j*.8,.55,Z+.3,5))})}
    else if(key==='publish2'){g.add(cy(.7,.85,.9,'#6b7787',cx,.8,Z+.4,18));const bt=cy(.5,.5,.22,'#e5483b',cx,1.38,Z+.4,18);g.add(bt);const rg=new THREE.Mesh(new THREE.TorusGeometry(.75,.05,6,28),new THREE.MeshBasicMaterial({color:'#ffd23f',transparent:true,opacity:.8}));rg.rotation.x=Math.PI/2;rg.position.set(cx,1.0,Z+.4);g.add(rg);anims.push(t=>{const u=(t*.9)%1;rg.scale.setScalar(1+u*.5);rg.material.opacity=.8*(1-u)})}
    else if(key==='publish3'){const r=cn(.45,1.9,'#ffffff',cx,2.0,Z+.3,12);g.add(r,cy(.46,.46,.2,'#e5483b',cx,1.2,Z+.3,12),bx(.12,.5,.5,'#e5483b',cx+.4,1.3,Z+.3),bx(.12,.5,.5,'#e5483b',cx-.4,1.3,Z+.3));g.add(bx(1.4,.2,1.0,'#6b7787',cx,.5,Z+.3));anims.push(t=>{r.position.y=2.0+Math.abs(Math.sin(t*1.5))*.2})}
    else if(key==='metrics0'){g.add(cy(.9,.2,.9,'#c9ced6',cx,2.3,Z+.2,14),cy(.18,.18,1.2,'#9aa2ad',cx,1.3,Z+.2,10),bx(1.4,.16,.9,'#6b7787',cx,.5,Z+.2));for(let j=0;j<5;j++){const d=sp(.1,'#58b4ff',cx,3.0,Z+.2,6);d.material=new THREE.MeshBasicMaterial({color:'#58b4ff'});g.add(d);anims.push(t=>{const u=((t*.5+j*.2)%1);d.position.set(cx+Math.sin(j*2+u*3)*.6,3.1-u*1.2,Z+.2)})}}
    else if(key==='metrics1'){g.add(cy(.07,.07,2.0,'#6b7787',cx,1.4,Z+.3,6),bx(2.0,.1,.1,'#6b7787',cx,2.3,Z+.3),bx(1.2,.12,.12,ink,cx,.45,Z+.3));[-.85,.85].forEach((x,j)=>{g.add(cy(.45,.45,.06,j?'#f5c542':'#9ed0ff',cx+x,1.7+j*.2,Z+.3,14),bx(.03,.5,.03,'#6b7787',cx+x,2.05+j*.1,Z+.3))})}
    else if(key==='metrics2'){board(cx,2.2,bz+.15,2.6,1.7,(c,w,h)=>{c.fillStyle='#10243a';c.fillRect(0,0,w,h);[40,70,55,90,110].forEach((v,j)=>{c.fillStyle=j===4?'#58e08a':'#58b4ff';c.fillRect(14+j*28,h-12-v*.7,20,v*.7)})});g.add(bx(1.0,.5,.5,'#4a4f57',cx,.62,Z+.6))}
    else if(key==='report0'){desk(cx,Z+.2,'#d9c9a3');g.add(bx(.7,.06,.5,'#ffffff',cx-.3,1.4,Z+.2),bx(.7,.04,.5,'#2a62c9',cx-.3,1.35,Z+.2),cy(.04,.04,.5,'#e5483b',cx+.5,1.5,Z+.25,5))}
    else if(key==='report1'){board(cx,2.25,bz+.15,2.8,1.8,(c,w,h)=>{c.fillStyle='#d9a56e';c.fillRect(0,0,w,h);[[18,20],[70,16],[120,26],[40,66],[100,70]].forEach(([x,y],j)=>{c.fillStyle=['#fff','#ffe27a','#9ed0ff','#ffb3c8','#fff'][j];c.fillRect(x,y,30,24)});c.strokeStyle='#c0392b';c.lineWidth=2;c.beginPath();c.moveTo(33,32);c.lineTo(85,28);c.lineTo(135,38);c.lineTo(115,80);c.lineTo(55,78);c.lineTo(33,32);c.stroke()})}
    else if(key==='report2'){g.add(bx(2.4,.5,1.2,'#7a5a3a',cx,.6,Z+.4));for(let j=0;j<5;j++){const sx=cx-.9+j*.45;g.add(cn(.14,.6+((j*7)%4)*.12,'#5cc66b',sx,1.2,Z+.4,5),sp(.14,'#7fd98a',sx+.12,1.2+((j*5)%3)*.12,Z+.5,6))}g.add(cy(.28,.34,.5,'#ffd23f',cx+1.5,.62,Z+.9,10))}
  },

  /* local house coordinates -> world */
  toWorld(k,x,y,z){const g=this.pl[k].g;g.updateMatrixWorld();return g.localToWorld(new THREE.Vector3(x,y,z))}
});
