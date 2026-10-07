/* ===== Sound: a small ambience per scenery plus little sound effects, all made on the spot with the Web Audio API
   (no audio files, nothing to download). Starts on your first tap or key, can be muted, and the choice is remembered. ===== */
Object.assign(ICON,{vol:'<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M15.5 9a4 4 0 010 6M18 6.5a8 8 0 010 11"/>',mute:'<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>'});
const Snd={ctx:null,on:true,master:null,bus:null,key:'',tod:'day',wx:'clear',buf:{},
  load(){try{this.on=localStorage.getItem('sv.snd')!=='0'}catch(e){this.on=true}if(Q.get('snd')==='0')this.on=false},
  /* browsers only allow sound after a tap or key press */
  unlock(){if(!this.on)return;try{if(!this.ctx){const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;this.ctx=new AC();this.master=this.ctx.createGain();this.master.gain.value=.7;this.master.connect(this.ctx.destination);
      const mk=(type)=>{const n=this.ctx.sampleRate*3,b=this.ctx.createBuffer(1,n,this.ctx.sampleRate),d=b.getChannelData(0);let l=0,b0=0,b1=0,b2=0;for(let i=0;i<n;i++){const w=Math.random()*2-1;if(type==='white')d[i]=w;else if(type==='brown'){l=(l+.02*w)/1.02;d[i]=l*3.5}else{b0=.99765*b0+w*.0990460;b1=.96300*b1+w*.2965164;b2=.57000*b2+w*1.0526913;d[i]=(b0+b1+b2+w*.1848)*.18}}return b};this.buf={white:mk('white'),pink:mk('pink'),brown:mk('brown')}}
    if(this.ctx.state==='suspended')this.ctx.resume();this.master.gain.setTargetAtTime(.7,this.ctx.currentTime,.1);if(this.key){const k=this.key;this.key='';this.scene(k)}}catch(e){}},
  toggle(){this.on=!this.on;try{localStorage.setItem('sv.snd',this.on?'1':'0')}catch(e){}if(this.on)this.unlock();else this.silence();return this.on},
  pause(){if(!this.ctx)return;this.stopBus(this.bus);this.bus=null;if(this.rainBus){this.stopBus(this.rainBus);this.rainBus=null}this.key=''},
  silence(){if(!this.ctx)return;this.master.gain.setTargetAtTime(0,this.ctx.currentTime,.08);this.stopBus(this.bus);this.bus=null;this.key=''},
  ok(){return this.on&&this.ctx&&this.ctx.state!=='closed'},
  /* ---------- building blocks ---------- */
  noise(type,dest,bus){const s=this.ctx.createBufferSource();s.buffer=this.buf[type];s.loop=true;s.loopStart=Math.random()*1.5;s.start();bus.src.push(s);return s},
  node(kind,v,q){const f=kind==='gain'?this.ctx.createGain():this.ctx.createBiquadFilter();if(kind==='gain')f.gain.value=v;else{f.type=kind;f.frequency.value=v;if(q)f.Q.value=q}return f},
  lfo(param,rate,depth,bus){const o=this.ctx.createOscillator(),g=this.ctx.createGain();o.frequency.value=rate;g.gain.value=depth;o.connect(g);g.connect(param);o.start();bus.src.push(o)},
  layer(bus,type,filt,f,q,vol){const n=this.noise(type,null,bus),fl=this.node(filt,f,q),g=this.node('gain',vol);n.connect(fl);fl.connect(g);g.connect(bus.g);return{fl,g}},
  tone(freq,dur,type,vol,o){o=o||{};const c=this.ctx,t=c.currentTime+(o.at||0),os=c.createOscillator(),g=c.createGain();os.type=type||'sine';os.frequency.setValueAtTime(freq,t);if(o.to)os.frequency.exponentialRampToValueAtTime(o.to,t+dur);
    g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(vol,t+(o.atk||.01));g.gain.exponentialRampToValueAtTime(.0001,t+dur);let last=os;if(o.filt){const f=c.createBiquadFilter();f.type=o.filt;f.frequency.value=o.ff||1200;os.connect(f);last=f}last.connect(g);g.connect(o.dest||this.master);os.start(t);os.stop(t+dur+.05)},
  puff(vol,dur,filt,f,o){o=o||{};const c=this.ctx,t=c.currentTime+(o.at||0),s=c.createBufferSource(),fl=this.node(filt,f,o.q),g=c.createGain();s.buffer=this.buf.white;g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(vol,t+(o.atk||.02));g.gain.exponentialRampToValueAtTime(.0001,t+dur);if(o.sweep)fl.frequency.exponentialRampToValueAtTime(o.sweep,t+dur);s.connect(fl);fl.connect(g);g.connect(o.dest||this.master);s.start(t,Math.random()*1.5);s.stop(t+dur+.05)},
  every(bus,a,b,fn){const go=()=>{if(bus.dead)return;if(this.ok())fn();setTimeout(go,a+Math.random()*(b-a))};setTimeout(go,a*Math.random()+200)},
  /* ---------- one ambience per scenery ---------- */
  scene(key){if(!this.ok()){this.key=key;return}if(key===this.key)return;this.key=key;const c=this.ctx,old=this.bus;this.stopBus(old);
    const bus={g:c.createGain(),src:[],dead:false};bus.g.gain.value=0;bus.g.connect(this.master);bus.g.gain.setTargetAtTime(1,c.currentTime,.9);this.bus=bus;
    const night=()=>this.tod==='night',day=()=>this.tod!=='night',self=this;
    const birds=(v)=>this.every(bus,1800,5200,()=>{if(night())return;const n=2+Math.floor(Math.random()*3),f=2400+Math.random()*1800;for(let i=0;i<n;i++)self.tone(f*(1+Math.random()*.15),.09,'sine',v,{at:i*.11,to:f*1.35,dest:bus.g})}),
      crickets=(v)=>this.every(bus,700,1600,()=>{if(day())return;const f=4300+Math.random()*400;for(let i=0;i<6;i++)self.tone(f,.04,'square',v*.5,{at:i*.07,filt:'bandpass',ff:f,dest:bus.g})}),
      chimes=(v,sc,a,b)=>this.every(bus,a,b,()=>{const n=sc[Math.floor(Math.random()*sc.length)];self.tone(261.6*Math.pow(2,n/12)*2,1.6,'sine',v,{atk:.005,dest:bus.g})}),
      wind=(v,f)=>{const l=this.layer(bus,'pink','lowpass',f||500,.6,v);this.lfo(l.g.gain,.07+Math.random()*.05,v*.6,bus)};
    const W=this.wx;
    if(key==='brand'){const l=this.layer(bus,'pink','bandpass',900,.5,.22);this.lfo(l.fl.frequency,.11,250,bus);wind(.05);birds(.05);crickets(.04)}
    else if(key==='ideas'){wind(.09,380);chimes(.07,[0,2,4,7,9,12],1100,3200);const l=this.layer(bus,'brown','lowpass',220,.5,.05);birds(.03);crickets(.03)}
    else if(key==='make'){const l=this.layer(bus,'brown','lowpass',160,.7,.16);this.lfo(l.g.gain,.8,.04,bus);const w=this.layer(bus,'pink','bandpass',700,.7,.07);this.every(bus,900,1500,()=>self.tone(95,.05,'square',.05,{dest:bus.g,filt:'lowpass',ff:400}));this.every(bus,4200,8800,()=>self.puff(.1,1.3,'highpass',2200,{dest:bus.g,atk:.2}));this.every(bus,16000,30000,()=>self.tone(520,.9,'sawtooth',.03,{to:640,filt:'lowpass',ff:900,dest:bus.g}))}
    else if(key==='review'){wind(.04,300);const l=this.layer(bus,'brown','lowpass',120,.5,.05);this.every(bus,1500,4200,()=>self.tone(500+Math.random()*350,.18,'sine',.08,{to:200,dest:bus.g}));crickets(.03);birds(.025)}
    else if(key==='publish'){const l=this.layer(bus,'pink','lowpass',650,.5,.18);this.lfo(l.g.gain,.16,.12,bus);this.lfo(l.fl.frequency,.16,260,bus);this.every(bus,2600,6500,()=>{if(night())return;const f=1200+Math.random()*500;self.tone(f,.5,'sawtooth',.03,{to:f*.62,filt:'bandpass',ff:1800,dest:bus.g})});this.every(bus,8000,16000,()=>{self.tone(660,1.8,'sine',.05,{dest:bus.g});self.tone(990,1.4,'sine',.03,{dest:bus.g})});this.every(bus,1200,2400,()=>self.puff(.04,.5,'bandpass',3000,{dest:bus.g}))}
    else if(key==='metrics'){[110,164.8,220,277.2].forEach((f,i)=>{const o=c.createOscillator(),g=c.createGain();o.frequency.value=f*(1+i*.001);o.type='sine';g.gain.value=.025;o.connect(g);g.connect(bus.g);o.start();bus.src.push(o);this.lfo(g.gain,.05+i*.02,.012,bus)});crickets(.06);chimes(.05,[0,4,7,12,16],2200,6000);this.every(bus,12000,26000,()=>self.puff(.07,1.6,'bandpass',1200,{dest:bus.g,sweep:5000,atk:.4}))}
    else if(key==='report'){wind(.1,900);const l=this.layer(bus,'pink','highpass',2500,.4,.025);this.lfo(l.g.gain,.2,.02,bus);this.every(bus,2200,6000,()=>{if(night())return;const n=2+Math.floor(Math.random()*2);for(let i=0;i<n;i++)self.tone(440+Math.random()*60,.28,'sawtooth',.03,{at:i*.35,to:330,filt:'bandpass',ff:900,dest:bus.g})});this.every(bus,9000,18000,()=>self.tone(70,1.4,'sawtooth',.04,{to:62,filt:'lowpass',ff:260,dest:bus.g}));crickets(.04);birds(.03)}
    else{wind(.08,500);const l=this.layer(bus,'pink','bandpass',500,.4,.04);this.lfo(l.g.gain,.1,.03,bus)}   // the world from above
    this.weather()},
  env(tod,wx){const ch=tod!==this.tod||wx!==this.wx;this.tod=tod;this.wx=wx;if(ch&&this.ok())this.weather()},
  weather(){if(!this.ctx)return;const c=this.ctx;if(this.rainBus){this.stopBus(this.rainBus);this.rainBus=null}if(this.wx==='rain'||this.wx==='snow'||this.wx==='desert'||this.wx==='fog'){const b={g:c.createGain(),src:[],dead:false};b.g.gain.value=0;b.g.connect(this.master);b.g.gain.setTargetAtTime(1,c.currentTime,.8);
      if(this.wx==='rain'){this.layer(b,'white','highpass',1400,.3,.16);this.layer(b,'pink','bandpass',700,.4,.07)}else if(this.wx==='snow')this.layer(b,'pink','lowpass',260,.4,.05);else if(this.wx==='desert'){const l=this.layer(b,'pink','bandpass',600,.5,.1);this.lfo(l.g.gain,.12,.07,b)}else this.layer(b,'brown','lowpass',140,.4,.06);this.rainBus=b}},
  stopBus(b){if(!b||!this.ctx)return;b.dead=true;b.g.gain.setTargetAtTime(0,this.ctx.currentTime,.35);setTimeout(()=>{b.src.forEach(s=>{try{s.stop()}catch(e){}});try{b.g.disconnect()}catch(e){}},2200)},
  /* ---------- effects ---------- */
  note(n){if(!this.ok())return;const f=261.6*Math.pow(2,n/12)*2;this.tone(f,1.4,'sine',.18,{atk:.005});this.tone(f*2,.8,'sine',.05,{atk:.005})},
  sfx(n){if(!this.ok())return;try{const T=(f,d,ty,v,o)=>this.tone(f,d,ty,v,o),P=(v,d,fl,f,o)=>this.puff(v,d,fl,f,o);
    ({splash:()=>{P(.22,.5,'bandpass',1800,{sweep:600});T(500,.2,'sine',.08,{to:200})},plop:()=>{T(620,.16,'sine',.2,{to:180});P(.07,.2,'bandpass',900)},chime:()=>{T(1046,.9,'sine',.16);T(1568,.7,'sine',.07,{at:.06})},
      steam:()=>{P(.25,1.1,'highpass',1800,{atk:.08});T(440,.7,'sawtooth',.05,{to:520,filt:'lowpass',ff:800})},wheel:()=>{for(let i=0;i<5;i++)T(120,.06,'square',.08,{at:i*.07,filt:'lowpass',ff:500});P(.1,.6,'bandpass',900)},gear:()=>{for(let i=0;i<4;i++)T(300+i*40,.05,'square',.06,{at:i*.05,filt:'bandpass',ff:900})},
      stone:()=>{T(180,.12,'triangle',.2,{to:90})},wave:()=>{P(.2,1.6,'lowpass',800,{atk:.5})},horn:()=>{T(196,.9,'sawtooth',.14,{filt:'lowpass',ff:500});T(247,.9,'sawtooth',.1,{filt:'lowpass',ff:500})},bell:()=>{[523,785,1170].forEach((f,i)=>T(f,1.8,'sine',.12/(i+1)))},
      pop:()=>{P(.35,.12,'highpass',700);T(900,.08,'sine',.15,{to:200})},bloop:()=>{T(260,.35,'sine',.2,{to:700})},whoosh:()=>{P(.18,1.1,'bandpass',500,{sweep:4800,atk:.3})},creak:()=>{T(130,.9,'sawtooth',.08,{to:90,filt:'lowpass',ff:420})},rustle:()=>{P(.2,1.2,'highpass',2600,{atk:.15})},
      quack:()=>{T(420,.16,'sawtooth',.16,{to:300,filt:'bandpass',ff:900});T(430,.14,'sawtooth',.12,{at:.2,to:280,filt:'bandpass',ff:900})},click:()=>{T(900,.03,'square',.05)},stamp:()=>{T(110,.18,'sine',.3,{to:60});P(.1,.1,'lowpass',900)},
      ding:()=>{T(1318,.7,'sine',.16);T(1975,.5,'sine',.06,{at:.04})},gate:()=>{T(150,.2,'square',.1,{to:80,filt:'lowpass',ff:500});T(220,.25,'sine',.08,{at:.12})},buzz:()=>{T(110,.5,'sawtooth',.1,{filt:'lowpass',ff:400})},
      fanfare:()=>{[523,659,784,1046].forEach((f,i)=>T(f,.5,'triangle',.16,{at:i*.11}))}}[n]||(()=>{}))()}catch(e){}},
  /* the simulation talks too, softly */
  event(kind){const m={'gate.review':'gate','gate.publish':'gate','review.approved':'stamp','publish.published':'fanfare','make.rendered':'ding','item.failed':'buzz','ideas.generated':'chime','brand.checked':'click'};if(m[kind])this.sfx(m[kind])}
};
