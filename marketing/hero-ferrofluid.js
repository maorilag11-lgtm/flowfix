/* ============================================================================
   Ferrofluid — fond anime du hero.
   Portage sans dependance du composant React Bits <Ferrofluid /> : meme shader,
   mais en WebGL brut, sans React ni ogl, pour rester sur un site statique.

   Reglages : <div class="hero-bg" data-*="..."> (voir DEFAULTS ci-dessous).
   Le canvas est purement decoratif — il est hors du flux, hors du clavier et
   hors des lecteurs d'ecran, donc il ne change rien au contenu indexe.
   ========================================================================== */
(function () {
  'use strict';

  var DEFAULTS = {
    colors: ['#5B45F0', '#7C4DF5', '#B79BFF'],
    speed: 0.28, scale: 1.6, turbulence: 1, fluidity: 0.1,
    rimWidth: 0.2, sharpness: 2.5, shimmer: 1.5, glow: 1.8,
    flow: 'down', opacity: 1,
    mouse: true, mouseStrength: 1, mouseRadius: 0.35, mouseDampening: 0.15
  };

  var VERT =
    'attribute vec2 position;attribute vec2 uv;varying vec2 vUv;' +
    'void main(){vUv=uv;gl_Position=vec4(position,0.0,1.0);}';

  var FRAG = [
    'precision highp float;',
    'uniform vec3 iResolution; uniform vec2 iMouse; uniform float iTime;',
    'uniform vec3 uColor0,uColor1,uColor2,uColor3,uColor4,uColor5,uColor6,uColor7;',
    'uniform int uColorCount; uniform vec2 uFlow;',
    'uniform float uSpeed,uScale,uTurbulence,uFluidity,uRimWidth,uSharpness,uShimmer,uGlow,uOpacity;',
    'uniform float uMouseEnabled,uMouseStrength,uMouseRadius;',
    'varying vec2 vUv;',
    '#define PI 3.14159265',
    'vec3 palette(float h){int c=uColorCount; if(c<1)c=1;',
    ' int i=int(floor(clamp(h,0.0,0.999999)*float(c)));',
    ' if(i<=0)return uColor0; if(i==1)return uColor1; if(i==2)return uColor2;',
    ' if(i==3)return uColor3; if(i==4)return uColor4; if(i==5)return uColor5;',
    ' if(i==6)return uColor6; return uColor7;}',
    'float hash(vec3 p3){p3=fract(p3*0.1031); p3+=dot(p3,p3.zyx+33.33); return fract((p3.x+p3.y)*p3.z);}',
    'float smin(float a,float b,float k){float r=exp2(-a/k)+exp2(-b/k); return -k*log2(r);}',
    'float sinlerp(float a,float b,float w){return mix(a,b,(sin(w*PI-PI/2.0)+1.0)/2.0);}',
    'float vn(vec2 p,float s,float seed){',
    ' vec2 cellp=floor(p/s); vec2 relp=mod(p,s);',
    ' float g1=hash(vec3(cellp,seed));',
    ' float g2=hash(vec3(cellp.x+1.0,cellp.y,seed));',
    ' float g3=hash(vec3(cellp.x+1.0,cellp.y+1.0,seed));',
    ' float g4=hash(vec3(cellp.x,cellp.y+1.0,seed));',
    ' float bx=sinlerp(g1,g2,relp.x/s); float tx=sinlerp(g4,g3,relp.x/s);',
    ' return sinlerp(bx,tx,relp.y/s);}',
    'float dbn(vec2 p,float s,float seed){float o=s/2.0;',
    ' float n0=vn(p,s,seed);',
    ' float n1=vn(p+vec2(o,o),s,seed+0.1);',
    ' float n2=vn(p+vec2(-o,o),s,seed+0.2);',
    ' float n3=vn(p+vec2(o,-o),s,seed+0.3);',
    ' float n4=vn(p+vec2(-o,-o),s,seed+0.4);',
    ' return (2.0*n0+1.5*n1+1.25*n2+1.125*n3+n4)/7.0;}',
    'void main(){',
    ' vec2 fragCoord=vUv*iResolution.xy;',
    ' float ref=700.0/max(uScale,0.05);',
    ' vec2 p=fragCoord/iResolution.y*ref;',
    ' float spd=200.0*uSpeed; float t=iTime;',
    ' vec2 dir=uFlow; vec2 perp=vec2(-dir.y,dir.x);',
    ' float d1=vn(p+perp*(t*spd),60.0,10.0)*50.0*uTurbulence;',
    ' float d2=vn(p-perp*(t*spd),120.0,15.0)*100.0*uTurbulence;',
    ' float peaks =dbn(p+d1+dir*(t*spd*0.5),40.0,1.0);',
    ' float peaks2=dbn(p+d2-dir*(t*spd*0.5),40.0,0.0);',
    ' float mapeaks=smin(peaks,peaks2,max(uFluidity,0.001));',
    ' float mGlow=0.0;',
    ' if(uMouseEnabled>0.5){',
    '   vec2 mp=iMouse/iResolution.y*ref;',
    '   float md=length(p-mp)/ref; float rr=max(uMouseRadius,0.02);',
    '   mGlow=exp(-md*md/(rr*rr))*uMouseStrength;}',
    ' float band=(uRimWidth-abs((mapeaks-0.4)*2.0))*5.0;',
    ' float ltn=clamp(band-vn(p+dir*(t*spd*0.5),60.0,12.0)*uShimmer,0.0,1.0);',
    ' ltn=pow(ltn,uSharpness)*uGlow;',
    ' ltn*=clamp(1.0-mGlow,0.0,1.0);',
    ' float h=clamp(0.5+(peaks-peaks2)*0.8,0.0,1.0);',
    ' vec3 outc=palette(h)*ltn;',
    ' float a=clamp(max(outc.r,max(outc.g,outc.b)),0.0,1.0);',
    ' gl_FragColor=vec4(outc,a*uOpacity);}'
  ].join('\n');

  function hexToRGB(hex) {
    var c = String(hex).replace('#', '');
    if (c.length === 3) c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
    c = (c + '000000').slice(0, 6);
    return [parseInt(c.slice(0, 2), 16) / 255,
            parseInt(c.slice(2, 4), 16) / 255,
            parseInt(c.slice(4, 6), 16) / 255];
  }
  function flowVec(d) {
    return d === 'up' ? [0, 1] : d === 'left' ? [-1, 0] : d === 'right' ? [1, 0] : [0, -1];
  }
  function num(el, key, fallback) {
    var v = parseFloat(el.getAttribute('data-' + key));
    return isNaN(v) ? fallback : v;
  }

  function build(gl) {
    function sh(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    }
    var pr = gl.createProgram();
    gl.attachShader(pr, sh(gl.VERTEX_SHADER, VERT));
    gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
    return pr;
  }

  function start(host) {
    /* Mouvement reduit ou economie de donnees : on ne lance rien d'anime.
       Le hero garde son degrade, personne ne paie un calcul inutile. */
    var conn = navigator.connection || navigator.webkitConnection;
    var saveData = !!(conn && (conn.saveData || /(^|-)2g$/.test(conn.effectiveType || '')));
    var still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    var gl = canvas.getContext('webgl', { alpha: true, antialias: false, premultipliedAlpha: false,
                                          powerPreference: 'low-power' })
          || canvas.getContext('experimental-webgl');
    if (!gl || saveData) { host.classList.add('hero-bg--still'); return; }

    var program;
    try { program = build(gl); }
    catch (e) { host.classList.add('hero-bg--still'); return; }

    host.appendChild(canvas);
    host.classList.add('hero-bg--on');

    /* un seul triangle couvre tout l'ecran */
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 0, 0, 3, -1, 2, 0, -1, 3, 0, 2]), gl.STATIC_DRAW);
    gl.useProgram(program);
    var aPos = gl.getAttribLocation(program, 'position');
    var aUv = gl.getAttribLocation(program, 'uv');
    gl.enableVertexAttribArray(aPos); gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(aUv);  gl.vertexAttribPointer(aUv, 2, gl.FLOAT, false, 16, 8);
    gl.clearColor(0, 0, 0, 0);

    var raw = host.getAttribute('data-colors');
    var colors = (raw ? raw.split(',') : DEFAULTS.colors).map(function (c) { return c.trim(); }).slice(0, 8);
    var count = Math.max(1, colors.length);
    var U = {};
    function loc(n) { return (U[n] = U[n] || gl.getUniformLocation(program, n)); }
    for (var i = 0; i < 8; i++) {
      gl.uniform3fv(loc('uColor' + i), hexToRGB(colors[Math.min(i, count - 1)]));
    }
    gl.uniform1i(loc('uColorCount'), count);
    gl.uniform2fv(loc('uFlow'), flowVec(host.getAttribute('data-flow') || DEFAULTS.flow));
    [['uSpeed', 'speed'], ['uScale', 'scale'], ['uTurbulence', 'turbulence'], ['uFluidity', 'fluidity'],
     ['uRimWidth', 'rimwidth'], ['uSharpness', 'sharpness'], ['uShimmer', 'shimmer'],
     ['uGlow', 'glow'], ['uOpacity', 'opacity'], ['uMouseStrength', 'mousestrength'],
     ['uMouseRadius', 'mouseradius']].forEach(function (pair) {
      var key = pair[1].replace('rimwidth', 'rimWidth').replace('mousestrength', 'mouseStrength')
                       .replace('mouseradius', 'mouseRadius');
      gl.uniform1f(loc(pair[0]), num(host, pair[1], DEFAULTS[key]));
    });

    /* scale = taille des motifs. Sur un ecran etroit, la valeur du bureau ne
       laisse voir qu'un seul filament perdu : on dezoome pour garder la meme
       densite de dessin qu'en grand. */
    var baseScale = num(host, 'scale', DEFAULTS.scale);
    var uScale = loc('uScale');

    /* la souris : pas de pointeur fin (telephone, tablette) = pas de calcul de pic */
    var fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    var wantMouse = fine && host.getAttribute('data-mouse') !== 'off';
    gl.uniform1f(loc('uMouseEnabled'), wantMouse ? 1 : 0);

    var uRes = loc('iResolution'), uTime = loc('iTime'), uMouse = loc('iMouse');
    var mouse = [0, 0], target = [0, 0];
    var damp = num(host, 'mousedampening', DEFAULTS.mouseDampening);

    /* Le canvas ne recoit pas les evenements (pointer-events: none) pour ne pas
       voler les clics des liens : on ecoute le hero lui-meme. */
    var surface = host.parentElement || host;
    if (wantMouse) {
      surface.addEventListener('pointermove', function (e) {
        var r = canvas.getBoundingClientRect();
        var sc = canvas.width / Math.max(r.width, 1);
        target = [(e.clientX - r.left) * sc, (r.height - (e.clientY - r.top)) * sc];
        if (damp <= 0) mouse = target.slice();
      }, { passive: true });
    }

    /* Resolution : plafonnee a 1.5 sur grand ecran et a 1 sur telephone.
       Au-dela, le gain visuel est nul et le GPU chauffe pour rien. */
    var w = 0, h = 0;
    function resize() {
      var r = host.getBoundingClientRect();
      var cap = window.innerWidth <= 860 ? 1 : 1.5;
      var dpr = Math.min(window.devicePixelRatio || 1, cap);
      var nw = Math.max(1, Math.round(r.width * dpr));
      var nh = Math.max(1, Math.round(r.height * dpr));
      if (nw === w && nh === h) return;
      w = canvas.width = nw; h = canvas.height = nh;
      gl.viewport(0, 0, w, h);
      gl.uniform3f(uRes, w, h, 1);
      gl.uniform1f(uScale, baseScale * (window.innerWidth <= 860 ? 0.55 : 1));
    }
    resize();
    if (window.ResizeObserver) new ResizeObserver(resize).observe(host);
    else window.addEventListener('resize', resize);

    function draw(time) {
      gl.uniform1f(uTime, time);
      gl.uniform2f(uMouse, mouse[0], mouse[1]);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    if (still) { draw(0); return; }   /* mouvement reduit : une image figee, puis plus rien */

    var raf = null, last = 0, visible = true;
    function loop(t) {
      raf = requestAnimationFrame(loop);
      var dt = last ? (t - last) / 1000 : 0;
      last = t;
      if (damp > 0) {
        var f = 1 - Math.exp(-dt / Math.max(1e-4, damp));
        if (f > 1) f = 1;
        mouse[0] += (target[0] - mouse[0]) * f;
        mouse[1] += (target[1] - mouse[1]) * f;
      } else { mouse = target.slice(); }
      draw(t * 0.001);
    }
    function play() { if (!raf && visible) { last = 0; raf = requestAnimationFrame(loop); } }
    function stop() { if (raf) { cancelAnimationFrame(raf); raf = null; } }

    /* On ne calcule rien quand le hero est hors de l'ecran ni quand l'onglet
       passe en arriere-plan : batterie du telephone preservee. */
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stop(); else play();
    });
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (en) {
        visible = en[0].isIntersecting;
        if (visible) play(); else stop();
      }, { threshold: 0 }).observe(host);
    } else { play(); }
    play();

    canvas.addEventListener('webglcontextlost', function (e) { e.preventDefault(); stop(); });
    canvas.addEventListener('webglcontextrestored', function () { play(); });
  }

  function init() {
    var host = document.querySelector('.hero-bg');
    if (host) start(host);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
