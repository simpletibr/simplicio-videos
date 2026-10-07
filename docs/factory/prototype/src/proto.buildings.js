/* ===== Seven kinds of building, one per stage, like a small town in a game:
   house (brand) · idea shop (ideas) · factory (make) · inspection garage (review) · market (publish) ·
   observatory (metrics) · barn (report). Each has rooms inside: the row of lamps on top lights up
   as the followed video moves through its sub-steps. ===== */
const BLD_OF={brand:'house',ideas:'lab',make:'factory',review:'garage',publish:'market',metrics:'observatory',report:'barn'};
const SUBS={brand:4,ideas:4,make:5,review:3,publish:4,metrics:3,report:3};
// where the stage icon sign hangs on each building (local units)
const SIGN={house:{y:1.0,s:.95,z:.935},lab:{y:1.78,s:.78,z:.86},factory:{y:1.08,s:.8,z:.97},garage:{y:1.28,s:.74,z:.93},market:{y:1.95,s:.82,z:.9},observatory:{y:.58,s:.78,z:.9},barn:{y:1.5,s:.72,z:.93}};

Object.assign(SceneThree,{
  makeBuilding(type,p,wm,anims){const g=new THREE.Group(),ink=p.ink,H=(m,k)=>hull(m,ink,k||1.04),base=bx(2.52,.12,2.12,shade(p.wall,-.16),0,.06,0);g.add(base);
    const win=(x,y,z,w,h)=>{const m=new THREE.Mesh(new THREE.BoxGeometry(w||.4,h||.4,.05),wm);m.position.set(x,y,z);g.add(m)},winS=(x,y,z)=>{const m=new THREE.Mesh(new THREE.BoxGeometry(.05,.4,.4),wm);m.position.set(x,y,z);g.add(m)};
    const smoke=(x,y,z,n,sc)=>{const puffs=[];for(let i=0;i<n;i++){const m=new THREE.Mesh(new THREE.SphereGeometry(.2,8,6),new THREE.MeshBasicMaterial({color:'#f2f4f7',transparent:true,opacity:0,depthWrite:false}));m.position.set(x,y,z);g.add(m);puffs.push({m,ph:i/n})}
      anims.push((t)=>{if(S.reduce)return;puffs.forEach(q=>{const u=((t*.28+q.ph)%1);q.m.position.y=y+u*1.5*(sc||1);q.m.position.x=x+u*.35;q.m.scale.setScalar(.5+u*1.5);q.m.material.opacity=.55*(1-u)*Math.min(1,u*6)})})};
    const stripes=(x,y,z,w,d,cols,rot)=>{const n=cols.length,gp=new THREE.Group();cols.forEach((c,i)=>gp.add(bx(w/n,.05,d,c,-w/2+w/n*(i+.5),0,0)));gp.position.set(x,y,z);gp.rotation.x=rot||0;g.add(gp)};
    let top=2.3;
    if(type==='house'){
      const roof=H(cn(1.75,1.0,p.roof,0,1.95,0,4),1.045);roof.rotation.y=Math.PI/4;g.add(H(bx(2.2,1.45,1.8,p.wall,0,.725,0)),roof,bx(2.34,.13,1.94,p.accent,0,1.47,0),bx(.34,.5,.34,shade(p.roof,-.2),.55,2.35,-.3));
      win(-.78,.8,.905);win(.78,.8,.905);winS(-1.1,.8,0);winS(1.1,.8,0);smoke(.55,2.65,-.3,3,.9);top=2.55}
    else if(type==='lab'){
      g.add(H(bx(2.1,2.0,1.7,p.wall,0,1.06,0)),bx(2.3,.14,1.9,p.roof,0,2.12,0),bx(2.3,.2,.1,p.accent,0,2.28,.92),bx(1.6,1.0,.05,'#bfe3ff',0,.78,.86));
      stripes(0,1.42,1.05,1.9,.55,[p.accent,'#ffffff',p.accent,'#ffffff',p.accent],.35);
      g.add(cy(.28,.05,.3,'#d9dde3',.6,2.4,0,10),sp(.17,'#ffe27a',-.5,2.5,0,10),cy(.02,.02,.5,ink,-.5,2.28,0,5));
      const bulb=g.children[g.children.length-2];bulb.material=new THREE.MeshLambertMaterial({color:'#fff1b8',emissive:'#ffd24a',emissiveIntensity:0});this.glow.push(bulb.material);win(0,.78,.9,1.6,.9);top=2.7}
    else if(type==='factory'){
      g.add(H(bx(2.3,1.15,1.9,shade(p.wall,-.06),0,.64,0)),bx(1.0,.82,.06,shade(ink,.25),0,.45,.96),bx(2.42,.1,2.0,shade(p.accent,-.1),0,1.24,0));
      const shp=new THREE.Shape();shp.moveTo(-.38,0);shp.lineTo(-.38,.55);shp.lineTo(.38,0);shp.closePath();
      [-.76,0,.76].forEach(x=>{const w=new THREE.Mesh(new THREE.ExtrudeGeometry(shp,{depth:1.9,bevelEnabled:false}),LM(p.roof));w.position.set(x,1.27,-.95);g.add(w);win(x-.3,1.35,.95,.35,.3)});
      [[-.75,.0],[-.3,.12]].forEach(([x,dy],i)=>{g.add(cy(.16,.2,1.2+dy*2,'#8e5a43',x,1.8+dy,-.5,10),cy(.17,.17,.12,p.accent,x,2.35+dy*2,-.5,10));smoke(x,2.5+dy*2,-.5,3,1)});
      win(-.8,.78,.96,.4,.34);win(.8,.78,.96,.4,.34);top=2.7}
    else if(type==='garage'){
      g.add(H(bx(2.2,1.3,1.8,p.wall,0,.71,0)),bx(2.44,.12,2.0,shade(p.roof,-.05),0,1.42,0),bx(1.5,.95,.06,'#c9ced6',0,.55,.93),bx(2.44,.1,.12,'#ffd23f',0,1.3,.98));
      [0,.25,.5,.75].forEach(y=>g.add(bx(1.5,.025,.07,'#9aa2ad',0,.2+y,.97)));
      for(let i=0;i<8;i++)g.add(bx(.3,.1,.14,i%2?'#10243a':'#ffd23f',-1.05+i*.3,1.3,1.0));
      g.add(cy(.03,.03,1.1,ink,1.0,1.95,.5,6),bx(.4,.28,.03,'#ffffff',1.2,2.3,.5),bx(.2,.14,.035,ink,1.1,2.37,.5),bx(.2,.14,.035,ink,1.3,2.23,.5));
      const lamp=sp(.14,'#ff5a4d',0,1.6,0,10);lamp.material=new THREE.MeshLambertMaterial({color:'#ff7a6d',emissive:'#ff3b2d',emissiveIntensity:.6});g.add(lamp);win(-.85,.9,.91);win(.85,.9,.91);top=2.5}
    else if(type==='market'){
      g.remove(base);g.add(bx(2.5,.12,2.1,shade(p.wall,-.1),0,.06,0),bx(2.3,.55,.14,p.wall,0,.4,-.85));
      const cols=[[p.roof,'#ffffff'],['#2f9a5a','#ffd23f'],['#e85d2a','#ffffff']];
      [-.78,0,.78].forEach((x,i)=>{g.add(H(bx(.66,.5,.6,shade(p.wall,-.05),x,.37,.15),1.05),cy(.025,.025,1.1,ink,x-.3,.9,.45,5),cy(.025,.025,1.1,ink,x+.3,.9,.45,5));
        stripes(x,1.38,.1,.78,.95,[cols[i][0],cols[i][1],cols[i][0],cols[i][1]],-.28);
        [['#e5483b',-.2],['#f5c542',0],['#5cc66b',.2]].forEach(([c,dx],j)=>g.add(bx(.14,.12,.14,c,x+dx,.68+(j%2)*.02,.2),sp(.07,c,x+dx,.78,.05,6)))});
      g.add(cy(.04,.05,2.2,ink,1.05,1.2,-.75,6));const fl=bx(.5,.3,.03,'#ffd23f',1.3,2.0,-.75);g.add(fl);anims.push((t)=>{fl.rotation.y=S.reduce?0:Math.sin(t*2.4)*.35});top=2.5}
    else if(type==='observatory'){
      g.add(H(bx(2.0,1.0,1.7,p.wall,0,.56,0)),H(cy(.78,.82,1.1,shade(p.wall,.04),0,1.62,0,18),1.04));
      const dome=new THREE.Mesh(new THREE.SphereGeometry(.84,18,10,0,Math.PI*2,0,Math.PI/2),LM(p.roof));dome.position.set(0,2.17,0);g.add(H(dome,1.03));
      g.add(bx(.2,.7,.5,shade(ink,.2),0,2.35,.55),Object.assign(cy(.08,.1,1.1,'#d9dde3',.2,2.55,.45,8),{}));g.children[g.children.length-1].rotation.x=-.9;
      win(-.55,.6,.9);win(.55,.6,.9);for(let i=0;i<3;i++)g.add(bx(.08,.16+i*.1,.04,'#ffffff',-.1+i*.14,.95,.93));top=3.15}
    else{ // barn
      g.add(H(bx(2.2,1.15,1.8,'#c8553d',0,.64,0)));
      [-1,1].forEach(s=>{const r=H(bx(1.35,.1,1.95,shade(p.roof,-.1),s*.55,1.62,0));r.rotation.z=-s*.55;g.add(r)});g.add(bx(.18,.1,1.95,shade(p.roof,-.2),0,1.97,0));
      g.add(bx(1.05,.88,.06,'#f2e6c9',0,.5,.93),bx(.06,.98,.07,'#ffffff',0,.5,.97));
      const x1=bx(.06,1.1,.07,'#ffffff',-.26,.5,.97),x2=bx(.06,1.1,.07,'#ffffff',.26,.5,.97);x1.rotation.z=.5;x2.rotation.z=-.5;g.add(x1,x2,bx(.42,.34,.05,'#f2e6c9',0,1.45,.93));
      [[1.25,.18,.5],[1.25,.18,.9],[1.25,.5,.7]].forEach(([x,y,z])=>g.add(bx(.45,.32,.4,'#f2c94c',x,y+.1,z-.2)));
      for(let i=0;i<4;i++)g.add(bx(.06,.45,.06,'#8a5a2b',-1.35,.3,.35+i*.34));g.add(bx(.05,.06,1.2,'#8a5a2b',-1.35,.5,.9));
      const vane=cn(.09,.3,'#ffd23f',0,2.25,0,5);vane.rotation.z=-Math.PI/2;g.add(cy(.02,.02,.5,ink,0,2.1,0,5),vane);anims.push((t)=>{vane.parent&&(vane.rotation.y=S.reduce?0:Math.sin(t*.9)*1.2)});
      win(0,1.55,.93,.0,.0);top=2.5}
    // the rooms inside: one lamp per sub-step, on a little rail above the roof
    const n=SUBS[this.curStage]||3,lamps=[];g.add(bx(n*.3+.2,.05,.12,shade(ink,.1),0,top-.02,0));
    for(let i=0;i<n;i++){const m=new THREE.MeshLambertMaterial({color:'#8c97a4',emissive:'#000000',emissiveIntensity:1});const l=new THREE.Mesh(new THREE.SphereGeometry(.1,10,8),m);l.position.set((i-(n-1)/2)*.3,top+.1,0);g.add(l);lamps.push(l)}
    return{g,top,lamps,sign:SIGN[type]}}
});
