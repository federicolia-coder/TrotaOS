// Trota OS website: the 3D scenes (hero trout, IoT network) and the scroll
// reveals. A tiny WebGL renderer written for this page, no library and no
// request to third parties. Without WebGL the static pictures stay in place;
// with "reduce motion" each scene is drawn once, still.
(function () {
  "use strict";
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Scroll reveals (editions stack, memory chart, support timeline) ----
  const revealed = document.querySelectorAll("[data-reveal]");
  if (!reduce && "IntersectionObserver" in window && revealed.length) {
    document.documentElement.classList.add("motion");
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }, { threshold: 0.35 });
    revealed.forEach((el) => io.observe(el));
  }

  // ---- Matrices (column-major, as WebGL expects) ----
  const ident = () => [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
  function mul(a, b) {
    const o = new Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      o[c * 4 + r] = s;
    }
    return o;
  }
  const chain = (...m) => m.reduce(mul);
  const tr = (x, y, z) => [1,0,0,0, 0,1,0,0, 0,0,1,0, x,y,z,1];
  const sc = (x, y, z) => [x,0,0,0, 0,y,0,0, 0,0,z,0, 0,0,0,1];
  const rx = (a) => { const c = Math.cos(a), s = Math.sin(a); return [1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1]; };
  const ry = (a) => { const c = Math.cos(a), s = Math.sin(a); return [c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1]; };
  const rz = (a) => { const c = Math.cos(a), s = Math.sin(a); return [c,s,0,0, -s,c,0,0, 0,0,1,0, 0,0,0,1]; };
  function persp(fov, aspect, near, far) {
    const f = 1 / Math.tan(fov / 2), nf = 1 / (near - far);
    return [f / aspect,0,0,0, 0,f,0,0, 0,0,(far + near) * nf,-1, 0,0,2 * far * near * nf,0];
  }
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  function lookAt(eye, at) {
    const z = norm(sub(eye, at)), x = norm(cross([0, 1, 0], z)), y = cross(z, x);
    return [x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0, -dot(x, eye),-dot(y, eye),-dot(z, eye),1];
  }
  const xf = (m, v, w) => [m[0] * v[0] + m[4] * v[1] + m[8] * v[2] + m[12] * w,
                           m[1] * v[0] + m[5] * v[1] + m[9] * v[2] + m[13] * w,
                           m[2] * v[0] + m[6] * v[1] + m[10] * v[2] + m[14] * w];
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const easeOut = (k) => 1 - Math.pow(1 - clamp(k, 0, 1), 3);
  const easeInOut = (k) => { k = clamp(k, 0, 1); return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; };

  // Colour: [r, g, b, emissive]
  const C = (hex, e) => [parseInt(hex.slice(1, 3), 16) / 255, parseInt(hex.slice(3, 5), 16) / 255, parseInt(hex.slice(5, 7), 16) / 255, e || 0];
  const ORANGE = C("#FF6A2A", 0.9);

  // ---- Geometry: flat-shaded triangles with per-vertex colour ----
  function Geo() { this.p = []; this.n = []; this.c = []; }
  Geo.prototype.tri = function (a, b, c, n, col) {
    for (const v of [a, b, c]) { this.p.push(v[0], v[1], v[2]); this.n.push(n[0], n[1], n[2]); this.c.push(col[0], col[1], col[2], col[3]); }
    return this;
  };
  // A 2D polygon (any simple polygon that is a fan from its first vertex), extruded along z.
  Geo.prototype.extrude = function (poly, z0, z1, col) {
    let area = 0;
    for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; area += a[0] * b[1] - b[0] * a[1]; }
    const sgn = area > 0 ? 1 : -1;
    for (let i = 1; i < poly.length - 1; i++) {
      const a = poly[0], b = poly[i], c = poly[i + 1];
      this.tri([a[0], a[1], z1], [b[0], b[1], z1], [c[0], c[1], z1], [0, 0, 1], col);
      this.tri([a[0], a[1], z0], [b[0], b[1], z0], [c[0], c[1], z0], [0, 0, -1], col);
    }
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length];
      const n = norm([(b[1] - a[1]) * sgn, -(b[0] - a[0]) * sgn, 0]);
      this.tri([a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], n, col);
      this.tri([a[0], a[1], z0], [b[0], b[1], z1], [a[0], a[1], z1], n, col);
    }
    return this;
  };
  Geo.prototype.box = function (x, y, z, w, h, d, col) {
    return this.extrude([[x - w / 2, y - h / 2], [x + w / 2, y - h / 2], [x + w / 2, y + h / 2], [x - w / 2, y + h / 2]], z - d / 2, z + d / 2, col);
  };
  Geo.prototype.cyl = function (x, y, z, r, h, seg, col) {
    for (let i = 0; i < seg; i++) {
      const a0 = i / seg * Math.PI * 2, a1 = (i + 1) / seg * Math.PI * 2, am = (a0 + a1) / 2;
      const p0 = [x + Math.cos(a0) * r, z + Math.sin(a0) * r], p1 = [x + Math.cos(a1) * r, z + Math.sin(a1) * r];
      const n = [Math.cos(am), 0, Math.sin(am)];
      this.tri([p0[0], y, p0[1]], [p1[0], y, p1[1]], [p1[0], y + h, p1[1]], n, col);
      this.tri([p0[0], y, p0[1]], [p1[0], y + h, p1[1]], [p0[0], y + h, p0[1]], n, col);
      this.tri([x, y + h, z], [p0[0], y + h, p0[1]], [p1[0], y + h, p1[1]], [0, 1, 0], col);
      this.tri([x, y, z], [p0[0], y, p0[1]], [p1[0], y, p1[1]], [0, -1, 0], col);
    }
    return this;
  };
  // Append another geometry transformed by matrix m (rigid transforms only).
  Geo.prototype.add = function (g, m) {
    for (let i = 0; i < g.p.length; i += 3) {
      const p = xf(m, [g.p[i], g.p[i + 1], g.p[i + 2]], 1), n = norm(xf(m, [g.n[i], g.n[i + 1], g.n[i + 2]], 0));
      this.p.push(p[0], p[1], p[2]); this.n.push(n[0], n[1], n[2]);
    }
    this.c.push(...g.c);
    return this;
  };

  // ---- Renderer ----
  const VS = "attribute vec3 aP;attribute vec3 aN;attribute vec4 aC;uniform mat4 uVP;uniform mat4 uM;" +
    "varying vec3 vN;varying vec3 vW;varying vec4 vC;" +
    "void main(){vec4 w=uM*vec4(aP,1.0);vW=w.xyz;vN=(uM*vec4(aN,0.0)).xyz;vC=aC;gl_Position=uVP*w;}";
  const FS = "precision mediump float;varying vec3 vN;varying vec3 vW;varying vec4 vC;" +
    "uniform vec3 uEye;uniform vec3 uKey;uniform vec3 uFog;uniform vec2 uFogR;uniform float uGlow;" +
    "void main(){vec3 n=normalize(vN);vec3 v=normalize(uEye-vW);if(dot(n,v)<0.0)n=-n;" +
    "vec3 b=vC.rgb;float hemi=0.5+0.5*n.y;vec3 col=b*mix(0.28,0.5,hemi);" +
    "float d=max(dot(n,uKey),0.0);col+=b*d*0.8;" +
    "vec3 h=normalize(uKey+v);col+=vec3(pow(max(dot(n,h),0.0),40.0)*0.28);" +
    "col+=vec3(1.0,0.42,0.16)*pow(1.0-max(dot(n,v),0.0),3.0)*0.12;" +
    "float e=clamp(vC.a+uGlow,0.0,1.0);col=mix(col,b*1.12+vec3(0.05),e*0.85);" +
    "col=mix(col,uFog,smoothstep(uFogR.x,uFogR.y,length(uEye-vW)));gl_FragColor=vec4(col,1.0);}";

  function Renderer(canvas) {
    const gl = canvas.getContext("webgl", { antialias: true, alpha: false, powerPreference: "low-power" });
    if (!gl) throw new Error("no webgl");
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("link");
    gl.useProgram(prog);
    const loc = {};
    for (const a of ["aP", "aN", "aC"]) loc[a] = gl.getAttribLocation(prog, a);
    for (const u of ["uVP", "uM", "uEye", "uKey", "uFog", "uFogR", "uGlow"]) loc[u] = gl.getUniformLocation(prog, u);
    gl.enable(gl.DEPTH_TEST);
    this.gl = gl; this.loc = loc; this.canvas = canvas;
  }
  Renderer.prototype.mesh = function (g) {
    const gl = this.gl, buf = (data) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW); return b; };
    return { p: buf(g.p), n: buf(g.n), c: buf(g.c), count: g.p.length / 3 };
  };
  Renderer.prototype.frame = function (view, bg, key, fogR) {
    const gl = this.gl, c = this.canvas, dpr = Math.min(devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(c.clientWidth * dpr)), h = Math.max(1, Math.round(c.clientHeight * dpr));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.uniformMatrix4fv(this.loc.uVP, false, view.vp);
    gl.uniform3fv(this.loc.uEye, view.eye); gl.uniform3fv(this.loc.uKey, norm(key));
    gl.uniform3fv(this.loc.uFog, bg); gl.uniform2fv(this.loc.uFogR, fogR);
  };
  Renderer.prototype.draw = function (m, model, glow) {
    const gl = this.gl, l = this.loc;
    for (const [a, b, n] of [["aP", m.p, 3], ["aN", m.n, 3], ["aC", m.c, 4]]) {
      gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.enableVertexAttribArray(l[a]); gl.vertexAttribPointer(l[a], n, gl.FLOAT, false, 0, 0);
    }
    gl.uniformMatrix4fv(l.uM, false, model); gl.uniform1f(l.uGlow, glow || 0);
    gl.drawArrays(gl.TRIANGLES, 0, m.count);
  };

  function camera(canvas, fov, eye, at) {
    const aspect = canvas.clientWidth / Math.max(1, canvas.clientHeight);
    return { eye, vp: mul(persp(fov, aspect, 0.1, 60), lookAt(eye, at)) };
  }
  function project(view, p, canvas) {
    const m = view.vp, x = m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12], y = m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
      w = m[3] * p[0] + m[7] * p[1] + m[11] * p[2] + m[15];
    return [(x / w * 0.5 + 0.5) * canvas.clientWidth, (0.5 - y / w * 0.5) * canvas.clientHeight];
  }
  function bgOf(el) {
    const m = getComputedStyle(el).backgroundColor.match(/[\d.]+/g) || [16, 18, 20];
    return [m[0] / 255, m[1] / 255, m[2] / 255];
  }

  // ---- Scene 1: the logo trout, extruded, turning towards the pointer ----
  function heroScene(canvas, section) {
    const r = new Renderer(canvas);
    const P = (x, y) => [(x - 128) / 100, -(y - 128) / 100];
    const poly = (pts) => pts.map((p) => P(p[0], p[1]));
    const LIGHT = C("#DDE1E5"), DARK = C("#101214");
    const parts = {
      tail: r.mesh(new Geo().extrude(poly([[52,128],[16,98],[28,128],[16,158]]), -0.09, 0.09, C("#C3C9CF"))),
      body: r.mesh(new Geo().extrude(poly([[60,128],[102,94],[198,94],[238,128],[198,162],[102,162]]), -0.09, 0.09, LIGHT)
        .box(P(210, 116)[0], P(210, 116)[1], 0, 0.08, 0.08, 0.205, DARK)
        .extrude(poly([[189,128],[180,101],[185,101],[194,128],[185,155],[180,155]]), -0.1, 0.1, DARK)),
      fin: r.mesh(new Geo().extrude(poly([[124,94],[142,76],[174,76],[164,94]]), -0.09, 0.09, C("#C3C9CF"))),
      band: r.mesh(new Geo().extrude(poly([[88,123],[214,123],[219,128],[214,133],[88,133],[83,128]]), -0.13, 0.13, ORANGE)),
    };
    // A tilted ring of small nodes around the fish: the devices it runs on.
    const node = r.mesh(new Geo().box(0, 0, 0, 0.075, 0.075, 0.075, C("#8C949C")));
    const packet = r.mesh(new Geo().box(0, 0, 0, 0.07, 0.07, 0.07, ORANGE));
    const dash = new Geo().box(0, 0, 0, 0.05, 0.007, 0.007, C("#3A4148"));
    const ring = new Geo();
    for (let i = 0; i < 90; i++) { const a = i / 90 * Math.PI * 2; ring.add(dash, chain(tr(Math.cos(a) * 1.6, 0, Math.sin(a) * 1.6), ry(-a - Math.PI / 2))); }
    const ringMesh = r.mesh(ring);
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    section.addEventListener("pointermove", (e) => {
      const b = canvas.getBoundingClientRect();
      pointer.tx = clamp((e.clientX - (b.left + b.width / 2)) / b.width, -1, 1);
      pointer.ty = clamp((e.clientY - (b.top + b.height / 2)) / b.height, -1, 1);
    });
    section.addEventListener("pointerleave", () => { pointer.tx = 0; pointer.ty = 0; });
    const RING = chain(tr(0, -0.05, 0), rx(0.32), rz(-0.12));
    return function render(t) {
      pointer.x += (pointer.tx - pointer.x) * 0.06; pointer.y += (pointer.ty - pointer.y) * 0.06;
      const bg = bgOf(section);
      const view = camera(canvas, 0.52, [0, 0.45, 7.0], [0, 0, 0]);
      r.frame(view, bg, [0.5, 0.8, 0.7], [6.7, 9.6]);
      const k = easeOut(t / 1.6);
      const yaw = -0.42 + 0.22 * Math.sin(t * 0.35) + pointer.x * 0.45;
      const pitch = 0.04 * Math.sin(t * 0.27) + pointer.y * 0.22;
      const fish = chain(tr(0, 0.04 * Math.sin(t * 0.7), 0), ry(yaw), rx(pitch));
      r.draw(parts.body, chain(fish, sc(0.85 + 0.15 * k, 0.85 + 0.15 * k, 0.85 + 0.15 * k)));
      r.draw(parts.tail, chain(fish, tr(-0.9 * (1 - k), 0, 0)));
      r.draw(parts.fin, chain(fish, tr(0, 0.7 * (1 - easeOut((t - 0.15) / 1.5)), 0)));
      const kb = easeOut((t - 0.35) / 1.4);
      r.draw(parts.band, chain(fish, tr(0, 0, 1.6 * (1 - kb)), sc(0.2 + 0.8 * kb, 1, 1)), 0.08 + 0.1 * (0.5 + 0.5 * Math.sin(t * 1.8)));
      const ringM = chain(RING, ry(t * 0.12), sc(0.7 + 0.3 * k, 0.7 + 0.3 * k, 0.7 + 0.3 * k));
      r.draw(ringMesh, ringM);
      for (let i = 0; i < 12; i++) {
        const a = i / 12 * Math.PI * 2;
        r.draw(node, chain(ringM, tr(Math.cos(a) * 1.6, 0, Math.sin(a) * 1.6), ry(t * 0.6 + i), rx(t * 0.4 + i * 2)));
      }
      const pa = -t * 0.9;
      r.draw(packet, chain(ringM, tr(Math.cos(pa) * 1.6, 0, Math.sin(pa) * 1.6), ry(t * 2)));
      return view;
    };
  }

  // ---- Scene 2: sensors -> gateway -> cloud -> screens, with data packets ----
  function iotScene(canvas, section, labels) {
    const r = new Renderer(canvas);
    const STEEL = C("#8C949C"), LIGHT = C("#DDE1E5"), MID = C("#AEB4BA"), DARK = C("#16191C"), LINE = C("#2E343A");
    const floor = new Geo();
    for (let i = 0; i < 18; i++) for (let j = 0; j < 7; j++)
      floor.box(-4.25 + i * 0.5, -0.025, -1.5 + j * 0.5, 0.47, 0.05, 0.47, (i + j) % 2 ? C("#15181B") : C("#181B1F"));
    const N = { s0: [-3.6, -0.85], s1: [-3.6, 0], s2: [-3.6, 0.85], g: [-1.25, 0], c: [1.25, 0], k0: [3.6, -0.6], k1: [3.6, 0.6] };
    const LINKS = [["s0", "g"], ["s1", "g"], ["s2", "g"], ["g", "c"], ["c", "k0"], ["c", "k1"]];
    for (const [a, b] of LINKS) {
      const A = N[a], B = N[b], dx = B[0] - A[0], dz = B[1] - A[1], len = Math.hypot(dx, dz);
      floor.add(new Geo().box(0, 0, 0, len, 0.012, 0.025, LINE), chain(tr((A[0] + B[0]) / 2, 0.006, (A[1] + B[1]) / 2), ry(-Math.atan2(dz, dx))));
    }
    const floorMesh = r.mesh(floor);
    // Devices, each built around its own origin so it can rise into place.
    const dev = {
      s0: new Geo().cyl(0, 0, 0, 0.18, 0.34, 14, MID).box(0, 0.36, 0, 0.1, 0.03, 0.1, STEEL),
      s1: new Geo().box(0, 0.15, 0, 0.42, 0.3, 0.3, STEEL).cyl(0.13, 0.3, -0.06, 0.018, 0.38, 6, MID),
      s2: new Geo().box(0, 0.2, 0, 0.46, 0.4, 0.26, LIGHT).box(-0.12, 0.2, 0.131, 0.05, 0.22, 0.004, DARK).box(0, 0.2, 0.131, 0.05, 0.22, 0.004, DARK),
      g: new Geo().box(0, 0.17, 0, 0.95, 0.34, 0.72, LIGHT).box(0, 0.11, 0.362, 0.6, 0.03, 0.006, ORANGE),
      c: new Geo(), k0: new Geo(), k1: new Geo(),
    };
    for (let i = 0; i < 3; i++) dev.c.box(0, 0.12 + i * 0.27, 0, 0.95, 0.23, 0.72, i === 1 ? LIGHT : MID).box(-0.25, 0.12 + i * 0.27, 0.362, 0.35, 0.025, 0.006, DARK);
    for (const k of ["k0", "k1"]) dev[k].box(0, 0.02, 0, 0.42, 0.04, 0.26, STEEL).cyl(0, 0.04, 0, 0.03, 0.5, 8, MID)
      .box(0, 0.86, 0, 0.98, 0.62, 0.05, STEEL).box(0, 0.86, 0.027, 0.88, 0.52, 0.006, C("#0B0C0E"));
    const devMesh = {}; for (const k in dev) devMesh[k] = r.mesh(dev[k]);
    const led = r.mesh(new Geo().box(0, 0, 0, 0.05, 0.05, 0.02, C("#FF6A2A", 0.35)));
    const cube = r.mesh(new Geo().box(0, 0, 0, 0.08, 0.08, 0.08, ORANGE));
    const bar = r.mesh(new Geo().box(0, 0.5, 0, 0.13, 1, 0.006, C("#FF6A2A", 0.6)));
    const LEDS = { s0: [0, 0.39, 0.06], s1: [-0.12, 0.2, 0.155], s2: [0.13, 0.32, 0.135], g: [0.36, 0.24, 0.365], c: [0.3, 0.39, 0.365], k0: [0.38, 1.12, 0.03], k1: [0.38, 1.12, 0.03] };
    // Packet timetable, repeating every PERIOD seconds.
    const PERIOD = 3.6, HOPS = [];
    for (let i = 0; i < 3; i++) {
      HOPS.push({ a: "s" + i, b: "g", t0: i * 0.35, d: 0.8 });
      HOPS.push({ a: "g", b: "c", t0: 1.3 + i * 0.3, d: 0.65 });
      HOPS.push({ a: "c", b: "k0", t0: 2.1 + i * 0.3, d: 0.6 });
      HOPS.push({ a: "c", b: "k1", t0: 2.15 + i * 0.3, d: 0.6 });
    }
    const ORDER = ["s0", "s1", "s2", "g", "c", "k0", "k1"];
    const rot = { k0: 0.25, k1: -0.1 };
    let start = null;
    return function render(t, fromStart) {
      if (start === null) start = t;
      const tv = fromStart ? 99 : t - start;     // seconds since the scene came into view
      const bg = bgOf(section);
      const aspect = canvas.clientWidth / Math.max(1, canvas.clientHeight);
      const R = 9.8 * Math.max(1, 2.1 / aspect), a = -0.42 + 0.06 * Math.sin(t * 0.12);
      const view = camera(canvas, 0.46, [Math.sin(a) * R, R * 0.6, Math.cos(a) * R], [0, 0.25, 0]);
      r.frame(view, bg, [-0.35, 0.9, 0.55], [R + 1.5, R + 9]);
      r.draw(floorMesh, ident());
      // Arrival times per device in the current cycle (for LEDs and dashboard bars).
      const cyc = t % PERIOD, since = {};
      for (const h of HOPS) {
        let dt = cyc - (h.t0 + h.d); if (dt < 0) dt += PERIOD;
        since[h.b] = Math.min(since[h.b] === undefined ? 9 : since[h.b], dt);
        let dl = cyc - h.t0; if (dl < 0) dl += PERIOD;
        since[h.a + "out"] = Math.min(since[h.a + "out"] === undefined ? 9 : since[h.a + "out"], dl);
      }
      ORDER.forEach((k, i) => {
        const rise = easeOut((tv - 0.12 * i) / 0.9);
        const M = chain(tr(N[k][0], -0.9 * (1 - rise), N[k][1]), ry(rot[k] || 0));
        r.draw(devMesh[k], M);
        const pulse = Math.exp(-6 * Math.min(since[k] === undefined ? 9 : since[k], since[k + "out"] === undefined ? 9 : since[k + "out"]));
        r.draw(led, chain(M, tr(LEDS[k][0], LEDS[k][1], LEDS[k][2])), rise * (0.15 + 0.85 * pulse));
        if (k[0] === "k") for (let b = 0; b < 4; b++) {
          const hgt = 0.12 + 0.07 * b + 0.08 * Math.exp(-4 * (since[k] || 0)) * ((b * 7 + Math.floor(t / PERIOD)) % 3) / 2;
          r.draw(bar, chain(M, tr(-0.27 + b * 0.18, 0.64, 0.032), sc(1, hgt * rise, 1)));
        }
      });
      if (tv > 1.2) for (const h of HOPS) {
        let u = cyc - h.t0; if (u < 0) u += PERIOD;
        u /= h.d; if (u > 1) continue;
        const e = easeInOut(u), A = N[h.a], B = N[h.b];
        r.draw(cube, chain(tr(A[0] + (B[0] - A[0]) * e, 0.12 + Math.sin(Math.PI * u) * 0.35, A[1] + (B[1] - A[1]) * e), ry(u * 3)));
      }
      for (const l of labels) {
        const p = N[l.dataset.at], [x, y] = project(view, [p[0], +l.dataset.h, p[1]], canvas);
        l.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(-50%,-100%)";
        l.style.opacity = clamp((tv - 0.6) / 0.6, 0, 1);
      }
      return view;
    };
  }

  // ---- Wiring: run each scene only while it is on screen ----
  const scenes = [];
  function setup(canvasId, fallbackId, build, sectionSel, extra) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const box = canvas.closest("[data-3d]") || canvas;
    try {
      box.hidden = false;
      const render = build(canvas, document.querySelector(sectionSel), extra);
      const fb = fallbackId && document.getElementById(fallbackId);
      if (fb) fb.hidden = true;
      scenes.push({ render, el: box, visible: false });
    } catch (e) {
      box.hidden = true;
    }
  }
  setup("trout3d", "facets", heroScene, ".hero");
  setup("iot3d", null, iotScene, "#iot", document.querySelectorAll(".iot3d-lbl"));
  if (!scenes.length) return;

  const t0 = performance.now();
  let raf = 0;
  function tick(now) {
    raf = 0;
    const t = (now - t0) / 1000;
    let any = false;
    for (const s of scenes) if (s.visible) { s.render(t); any = true; }
    if (any) raf = requestAnimationFrame(tick);
  }
  function still() { for (const s of scenes) s.render(30, true); }
  if (reduce) {
    still();
    addEventListener("resize", still);
    return;
  }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) { const s = scenes.find((x) => x.el === e.target); if (s) s.visible = e.isIntersecting; }
    if (!raf && scenes.some((s) => s.visible)) raf = requestAnimationFrame(tick);
  });
  scenes.forEach((s) => io.observe(s.el));
})();
