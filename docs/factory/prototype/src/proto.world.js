/* ===== A living world around the factory: weather (sun, rain, snow, desert, fog), clouds, birds, a plane,
   a lake with boats and jumping fish, fireflies at night. All procedural, all cheap, zero tokens. ===== */
const WX_ORDER=['clear','rain','snow','desert','fog'];
const WX={clear:{},
  rain:{sky:'#5f7185',k:.75,hemi:.72,sun:.4,fog:.5},
  snow:{sky:'#e4edf7',k:.65,hemi:1.05,sun:.7,fog:.55,ground:'#eef3fb',gk:.9},
  desert:{sky:'#f0cf9a',k:.5,hemi:1,sun:1.05,sunc:'#ffd9a0',fog:1,ground:'#e0c28a',gk:1},
  fog:{sky:'#c9d3dc',k:.85,hemi:.9,sun:.5,fog:.3}};

const KW=K3;
Object.assign(SceneThree,{
  buildWorld(){const W=this.world,P=(x,y,z)=>new THREE.Vector3(x,y,z),mb=c=>new THREE.MeshBasicMaterial({color:c}),ml=c=>new THREE.MeshLambertMaterial({color:c,flatShading:true});
    const rnd=(()=>{let a=7;return()=>{a=(a*16807)%2147483647;return(a-1)/2147483646}})();this.amb={};
    // clouds
    const cm=new THREE.MeshLambertMaterial({color:'#ffffff',flatShading:true});this.clouds=[];
    for(let i=0;i<6;i++){const g=new THREE.Group();[[0,0,0,1.5],[1.4,-.2,.3,1.1],[-1.3,-.15,-.2,1],[.4,.4,0,1]].forEach(([x,y,z,r])=>{const m=new THREE.Mesh(new THREE.SphereGeometry(r,8,6),cm);m.position.set(x,y,z);g.add(m)});
      g.position.set((-34+i*13)*KW,(12+(i%3)*1.8)*1.4,(-26+(i%2)*9)*KW);g.scale.set(2.4,1.3,1.8);g.userData.sp=.3+(i%3)*.12;W.add(g);this.clouds.push(g)}
    // birds: two flocks circling
    const bw=new THREE.BufferGeometry();bw.setAttribute('position',new THREE.BufferAttribute(new Float32Array([-.18,0,0,.22,0,0,0,0,.9]),3));bw.computeVertexNormals();
    const bmat=new THREE.MeshBasicMaterial({color:'#31404f',side:THREE.DoubleSide});this.flocks=[];
    [[-6,-10,26,16,.16],[14,4,19,13,-.22]].forEach(([cx,cz,r,h,w],fi)=>{const grp=new THREE.Group(),birds=[];
      for(let i=0;i<5;i++){const b=new THREE.Group(),l=new THREE.Mesh(bw,bmat),r2=new THREE.Mesh(bw,bmat);r2.scale.z=-1;b.add(l,r2);b.userData={l,r:r2,off:(i-2)*.9,back:Math.abs(i-2)*.8,ph:i*.7};grp.add(b);birds.push(b)}
      W.add(grp);this.flocks.push({grp,birds,cx,cz,r,h,w,t:fi*2})});
    // airplane with a contrail, crosses every ~50 s
    const plane=new THREE.Group(),fus=new THREE.Mesh(new THREE.CylinderGeometry(.28,.2,2.6,8),ml('#f4f6fa'));fus.rotation.z=Math.PI/2;plane.add(fus,
      at(new THREE.Mesh(new THREE.BoxGeometry(.7,.06,3.2),ml('#e6ebf2')),.1,0,0),at(new THREE.Mesh(new THREE.BoxGeometry(.4,.06,1.1),ml('#e6ebf2')),-1.15,.05,0),
      at(new THREE.Mesh(new THREE.BoxGeometry(.5,.55,.06),ml('#ff5a4d')),-1.15,.32,0),at(new THREE.Mesh(new THREE.SphereGeometry(.26,8,6),ml('#9ed0ff')),.85,.12,0));
    plane.position.set(-90,26,-30);W.add(plane);this.plane={g:plane,t:-8,trail:[]};
    const tm=new THREE.MeshBasicMaterial({color:'#ffffff',transparent:true,opacity:.7,depthWrite:false});
    for(let i=0;i<22;i++){const m=new THREE.Mesh(new THREE.SphereGeometry(.22,6,5),tm.clone());m.visible=false;W.add(m);this.plane.trail.push({m,age:9})}
    // lake with boats and fish (pan left to find it)
    const lake=new THREE.Group();lake.position.set(-40*KW/1.78*1.0-6,0,6);W.add(lake);this.lake=lake;
    const wt=ctex(256,256,(g,w,h)=>{const gr=g.createLinearGradient(0,0,w,h);gr.addColorStop(0,'#6fc3f2');gr.addColorStop(1,'#2f8fd0');g.fillStyle=gr;g.fillRect(0,0,w,h);g.strokeStyle='rgba(255,255,255,.35)';g.lineWidth=3;for(let i=0;i<14;i++){const x=(i*61)%w,y=(i*37)%h;g.beginPath();g.arc(x,y,10+(i%4)*6,.2,Math.PI-.2);g.stroke()}});wt.wrapS=wt.wrapT=THREE.RepeatWrapping;wt.repeat.set(2,2);this.waterTex=wt;
    const water=new THREE.Mesh(new THREE.CircleGeometry(1,40),new THREE.MeshBasicMaterial({map:wt}));water.rotation.x=-Math.PI/2;water.position.y=.03;water.scale.set(11,7.5,1);lake.add(water);
    const rim=new THREE.Mesh(new THREE.TorusGeometry(1,.035,6,40),ml('#d9c9a3'));rim.rotation.x=Math.PI/2;rim.position.y=.05;rim.scale.set(11.2,7.7,1);lake.add(rim);
    this.boats=[];
    const sail=()=>{const g=new THREE.Group(),hull=new THREE.Mesh(new THREE.BoxGeometry(1.5,.28,.55),ml('#c0392b'));hull.position.y=.18;const mast=new THREE.Mesh(new THREE.CylinderGeometry(.03,.03,1.5,5),ml('#6b4a2a'));mast.position.set(.1,.95,0);
      const sg=new THREE.BufferGeometry();sg.setAttribute('position',new THREE.BufferAttribute(new Float32Array([.12,1.65,0,.12,.35,0,-.7,.38,0]),3));sg.computeVertexNormals();g.add(hull,mast,new THREE.Mesh(sg,new THREE.MeshBasicMaterial({color:'#ffffff',side:THREE.DoubleSide})));return g};
    const ferry=()=>{const g=new THREE.Group(),hull=new THREE.Mesh(new THREE.BoxGeometry(2.6,.4,.9),ml('#2a62c9'));hull.position.y=.25;const cab=new THREE.Mesh(new THREE.BoxGeometry(1.2,.5,.7),ml('#f5f1e6'));cab.position.set(-.2,.7,0);const fun=new THREE.Mesh(new THREE.CylinderGeometry(.14,.14,.4,8),ml('#ffd23f'));fun.position.set(-.5,1.12,0);const win=new THREE.Mesh(new THREE.BoxGeometry(.9,.18,.72),mb('#9ed0ff'));win.position.set(-.2,.78,0);g.add(hull,cab,fun,win);return g};
    const kayak=()=>{const g=new THREE.Group(),h=new THREE.Mesh(new THREE.CapsuleGeometry(.14,.9,3,8),ml('#ffd23f'));h.rotation.z=Math.PI/2;h.position.y=.12;g.add(h);return g};
    [[sail,.35,.0,.75,.62],[ferry,.18,2.4,.55,.38],[kayak,.6,4.1,.4,.3]].forEach(([mk,w,ph,rx,rz])=>{const b=mk();lake.add(b);this.boats.push({g:b,w,ph,rx,rz})});
    this.fish=[];const fm=ml('#cfe4f2');for(let i=0;i<3;i++){const f=new THREE.Mesh(new THREE.SphereGeometry(.2,8,6),fm);f.scale.set(1.6,.7,.7);f.visible=false;lake.add(f);const rg=new THREE.Mesh(new THREE.RingGeometry(.2,.28,20),new THREE.MeshBasicMaterial({color:'#ffffff',transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false}));rg.rotation.x=-Math.PI/2;rg.position.y=.06;lake.add(rg);this.fish.push({f,rg,t:-i*1.3-1,x:0,z:0})}
    // weather particles
    const box=(n,fn)=>{const a=new Float32Array(n*3);for(let i=0;i<n;i++){const v=fn(i);a[i*3]=v[0];a[i*3+1]=v[1];a[i*3+2]=v[2]}return a};
    const rainA=box(700*2,i=>[(rnd()-.5)*110,rnd()*34,(rnd()-.5)*90]);const rg=new THREE.BufferGeometry();rg.setAttribute('position',new THREE.BufferAttribute(rainA,3));
    this.rain=new THREE.LineSegments(rg,new THREE.LineBasicMaterial({color:'#d8e8ff',transparent:true,opacity:.55}));this.rain.visible=false;this.rain.frustumCulled=false;W.add(this.rain);this.rainN=700;
    const mkPts=(n,col,size,op)=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(box(n,()=>[(rnd()-.5)*110,rnd()*28,(rnd()-.5)*90]),3));const p=new THREE.Points(g,new THREE.PointsMaterial({color:col,size,transparent:true,opacity:op,depthWrite:false}));p.visible=false;p.frustumCulled=false;W.add(p);return p};
    this.snow=mkPts(900,'#ffffff',.26,.95);this.dust=mkPts(420,'#e9c88f',.2,.6);this.flies=mkPts(70,'#ffe27a',.3,1);this.flies.material.blending=THREE.AdditiveBlending;
    // desert props (only shown in the desert): cacti and rocks around the plaza
    this.cacti=new THREE.Group();[[-26,-6],[27,-10],[-27,9],[28,8],[-11,-17],[14,-18],[-4,17],[22,16]].forEach(([x,z],i)=>{const g=new THREE.Group(),c=ml('#4f9a52');g.add(at(new THREE.Mesh(new THREE.CylinderGeometry(.28,.32,2.4,8),c),0,1.2,0),at(new THREE.Mesh(new THREE.CylinderGeometry(.18,.2,1,6),c),.5,1.5,0),at(new THREE.Mesh(new THREE.CylinderGeometry(.18,.2,.9,6),c),-.5,1.2,0));g.position.set(x,0,z);g.scale.setScalar(.9+i*.07);g.traverse(o=>{if(o.isMesh){o.castShadow=true}});this.cacti.add(g)});
    const rk=ml('#b88a5a');[[-17,14],[18,15],[-30,-12],[31,-2]].forEach(([x,z],i)=>{const r=new THREE.Mesh(new THREE.DodecahedronGeometry(.9+i*.2,0),rk);r.position.set(x,.4,z);r.castShadow=true;this.cacti.add(r)});this.cacti.visible=false;W.add(this.cacti);
    this.windX=0},
  drawWorld(T,dt){const wx=S.wx||'clear',night=S.tod==='night',R=S.reduce;
    // clouds drift and wrap
    for(const c of this.clouds){c.position.x+=dt*c.userData.sp*(R?0:1);if(c.position.x>46)c.position.x=-46;c.visible=wx!=='desert'||true}
    // birds
    const birdsOn=(wx==='clear'||wx==='desert')&&!night;for(const f of this.flocks){f.grp.visible=birdsOn;if(!birdsOn)continue;f.t+=dt*f.w;const a=f.t;
      f.grp.position.set(f.cx+Math.cos(a)*f.r,f.h+Math.sin(a*1.7)*.6,f.cz+Math.sin(a)*f.r*.55);f.grp.rotation.y=-a+(f.w>0?Math.PI:0)+(f.w>0?0:Math.PI);
      f.birds.forEach(b=>{b.position.set(-b.userData.back,0,b.userData.off);const fl=Math.sin(T*9+b.userData.ph)*.7;b.userData.l.rotation.x=fl;b.userData.r.rotation.x=-fl})}
    // plane + contrail
    const pl=this.plane;pl.t+=dt;if(pl.t>50)pl.t=-6;const run=pl.t>=0&&pl.t<=26&&wx!=='rain'&&wx!=='fog';pl.g.visible=run;
    if(run){const x=-90+pl.t*7.2;pl.g.position.set(x,26+Math.sin(pl.t*.4)*.8,-30+pl.t*.3);pl.g.scale.setScalar(1.8);pl.g.rotation.y=Math.PI;pl.g.rotation.z=Math.sin(pl.t*.7)*.06;
      pl.acc=(pl.acc||0)+dt;if(pl.acc>.16){pl.acc=0;const s=pl.trail.reduce((a,b)=>b.age>a.age?b:a);s.age=0;s.m.position.copy(pl.g.position).add(new THREE.Vector3(-1.6,0,0));s.m.visible=true}}
    for(const s of pl.trail){s.age+=dt;if(s.age>3.5)s.m.visible=false;else if(s.m.visible){const k=1-s.age/3.5;s.m.scale.setScalar(.5+s.age*.5);s.m.material.opacity=.7*k}}
    // lake
    this.waterTex.offset.x+=dt*.02;this.waterTex.offset.y+=dt*.012;
    this.boats.forEach(b=>{const a=T*b.w+b.ph;b.g.position.set(Math.cos(a)*8.6*b.rx,.0+Math.sin(T*1.6+b.ph)*.06,Math.sin(a)*5.8*b.rz*1.2);b.g.scale.setScalar(1.7);b.g.rotation.y=-a+Math.PI;b.g.rotation.z=Math.sin(T*1.3+b.ph)*.05});
    this.fish.forEach(f=>{f.t+=dt;if(f.t<0){f.f.visible=false;f.rg.material.opacity=0;f.fresh=true;return}
      if(f.fresh){f.fresh=false;const a=Math.random()*6.28,r=Math.random()*.7;f.x=Math.cos(a)*r*8.5;f.z=Math.sin(a)*r*5.4}
      const d=1.1;if(f.t<d){const u=f.t/d;f.f.visible=true;f.f.position.set(f.x+u*1.4,Math.sin(u*Math.PI)*1.1,f.z);f.f.rotation.z=Math.cos(u*Math.PI)*.8}
      else if(f.t<d+2.4){const u=(f.t-d)/2.4;f.f.visible=false;f.rg.position.set(f.x+1.4,.06,f.z);f.rg.scale.setScalar(1+u*5);f.rg.material.opacity=.8*(1-u)}
      else f.t=-(1+Math.random()*3)});
    // weather particles
    const wind=Math.sin(T*.2)*1.2;
    if(this.rain.visible){const p=this.rain.geometry.attributes.position,n=this.rainN;for(let i=0;i<n;i++){let y=p.getY(i*2)-dt*32;if(y<0)y+=34;const x=p.getX(i*2)+dt*3,z=p.getZ(i*2);p.setXYZ(i*2,x>55?x-110:x,y,z);p.setXYZ(i*2+1,(x>55?x-110:x)+.16,y+1.3,z)}p.needsUpdate=true}
    if(this.snow.visible){const p=this.snow.geometry.attributes.position;for(let i=0;i<900;i++){let y=p.getY(i)-dt*(1.4+(i%5)*.25);if(y<0)y+=28;p.setXYZ(i,p.getX(i)+Math.sin(T*.8+i)*.01+wind*dt*.4,y,p.getZ(i))}p.needsUpdate=true}
    if(this.dust.visible){const p=this.dust.geometry.attributes.position;for(let i=0;i<420;i++){let x=p.getX(i)+dt*(3+(i%4)*.5);if(x>55)x-=110;p.setXYZ(i,x,p.getY(i)+Math.sin(T*1.5+i)*.012,p.getZ(i))}p.needsUpdate=true}
    if(this.flies.visible){const p=this.flies.geometry.attributes.position;for(let i=0;i<70;i++){p.setXYZ(i,p.getX(i)+Math.sin(T*.7+i)*.01,Math.max(.4,Math.min(5,p.getY(i)+Math.cos(T*.9+i*1.7)*.01)),p.getZ(i)+Math.cos(T*.6+i)*.01)}p.needsUpdate=true;this.flies.material.opacity=.55+Math.sin(T*3)*.35}},
  applyWx(){if(!this.scn)return;const wx=S.wx||'clear',n=S.tod==='night';
    this.rain.visible=wx==='rain';this.snow.visible=wx==='snow';this.dust.visible=wx==='desert';this.flies.visible=n&&(wx==='clear'||wx==='desert');this.cacti.visible=wx==='desert'}
});
