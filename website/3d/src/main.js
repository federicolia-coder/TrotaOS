// Trota OS website: the 3D scenes (hero trout, IoT network) and the scroll
// reveals. Built with three.js into website/root/trota-3d.js (see package.json);
// everything is served by the site, nothing is fetched from third parties.
// Without WebGL the static pictures stay; with "reduce motion" each scene is
// drawn once, still.
import {
  CatmullRomCurve3, Color, DirectionalLight, Fog, Group, HemisphereLight, InstancedMesh, Mesh,
  MeshBasicMaterial, MeshStandardMaterial, NeutralToneMapping, Object3D, PCFShadowMap, PerspectiveCamera,
  PlaneGeometry, PMREMGenerator, RingGeometry, Scene, ShadowMaterial, SphereGeometry, TorusGeometry,
  TubeGeometry, Vector3, WebGLRenderer, QuadraticBezierCurve3,
} from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { MAT, ORANGE, cloud, glow, kiosk, laptop, meter, minipc, radio, sensor, server, trout } from "./models.js";

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

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const easeOut = (k) => 1 - Math.pow(1 - clamp(k, 0, 1), 3);
const easeInOut = (k) => { k = clamp(k, 0, 1); return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; };
const bgOf = (el) => new Color(getComputedStyle(el).backgroundColor);

// Renderer, environment light and resize handling shared by both scenes.
function stage(canvas, section, fov, rimI = 1.4, rimC = 0xff8a50) {
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.toneMapping = NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = PCFShadowMap;
  const scene = new Scene();
  const pmrem = new PMREMGenerator(renderer), room = new RoomEnvironment();
  scene.environment = pmrem.fromScene(room, 0.04).texture;
  scene.environmentIntensity = 0.4;
  room.dispose(); pmrem.dispose();
  const camera = new PerspectiveCamera(fov, 1, 0.1, 80);
  const paint = () => { const bg = bgOf(section); scene.background = bg; if (scene.fog) scene.fog.color.copy(bg); };
  paint();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paint);
  scene.add(new HemisphereLight(0xdfe6ee, 0x0b0c0e, 0.7));
  // Warm rim from behind: the brand orange catches the bevels.
  const rim = new DirectionalLight(rimC, rimI); rim.position.set(-4, 2.5, -5); scene.add(rim);
  function fit() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    const size = renderer.getSize(new Vector3());
    if (w && h && (size.x !== w || size.y !== h)) { renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
  }
  return { renderer, scene, camera, fit };
}

function keyLight(scene, x, y, z, extent, size) {
  const key = new DirectionalLight(0xffffff, 2.4);
  key.position.set(x, y, z);
  key.castShadow = true;
  key.shadow.mapSize.set(size, size);
  Object.assign(key.shadow.camera, { left: -extent, right: extent, top: extent, bottom: -extent, near: 0.5, far: 30 });
  key.shadow.camera.updateProjectionMatrix();
  key.shadow.radius = 5;
  key.shadow.normalBias = 0.02;
  key.shadow.bias = -0.0002;
  scene.add(key);
  return key;
}

// ---- Scene 1: the logo trout, turning towards the pointer, with its devices around ----
function heroScene(canvas, section) {
  const { renderer, scene, camera, fit } = stage(canvas, section, 30);
  camera.position.set(0, 0.5, 7.2); camera.lookAt(0, -0.1, 0);
  scene.fog = new Fog(scene.background, 7, 11);
  keyLight(scene, 2.5, 6, 4, 3, 1024);

  const fish = trout();
  const holder = new Group();
  fish.group.scale.setScalar(0.0105);
  holder.add(fish.group);
  scene.add(holder);
  const catcher = new Mesh(new PlaneGeometry(8, 8), new ShadowMaterial({ opacity: 0.32 }));
  catcher.rotation.x = -Math.PI / 2; catcher.position.y = -1.35; catcher.receiveShadow = true;
  scene.add(catcher);

  // The ring of devices: laptop, server, screen, sensor, mini PC, cloud.
  const ring = new Group();
  ring.rotation.set(0.3, 0, -0.1); ring.position.y = -0.1;
  scene.add(ring);
  const R = 1.85;
  const track = new Mesh(new TorusGeometry(R, 0.004, 6, 220), new MeshBasicMaterial({ color: 0x3a4148 }));
  track.rotation.x = Math.PI / 2;
  ring.add(track);
  const spin = new Group(); ring.add(spin);
  const devices = [laptop(), server(), kiosk(), sensor(), minipc(), cloud()];
  devices.forEach((d, i) => {
    const a = i / devices.length * Math.PI * 2, holderD = new Group();
    holderD.position.set(Math.cos(a) * R, 0, Math.sin(a) * R);
    holderD.rotation.y = Math.PI / 2 - a;
    d.group.scale.setScalar(0.34);
    d.group.position.y = -d.height * 0.17;
    d.group.traverse((o) => { o.castShadow = false; });
    holderD.add(d.group);
    spin.add(holderD);
    const b = new Mesh(new SphereGeometry(0.022, 16, 12), MAT.steel);
    b.position.set(Math.cos(a + Math.PI / 6) * R, 0, Math.sin(a + Math.PI / 6) * R);
    spin.add(b);
  });
  const packet = new Group();
  packet.add(new Mesh(new SphereGeometry(0.035, 20, 14), MAT.orange), glow(0.42));
  ring.add(packet);
  const trail = [0.05, 0.1, 0.15, 0.2].map((d, i) => { const s = glow(0.28 - i * 0.05); s.material.opacity = 0.55 - i * 0.12; ring.add(s); return { d, s }; });

  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  section.addEventListener("pointermove", (e) => {
    const b = canvas.getBoundingClientRect();
    pointer.tx = clamp((e.clientX - (b.left + b.width / 2)) / b.width, -1, 1);
    pointer.ty = clamp((e.clientY - (b.top + b.height / 2)) / b.height, -1, 1);
  });
  section.addEventListener("pointerleave", () => { pointer.tx = 0; pointer.ty = 0; });

  return function render(t) {
    fit();
    pointer.x += (pointer.tx - pointer.x) * 0.06; pointer.y += (pointer.ty - pointer.y) * 0.06;
    const k = easeOut(t / 1.6), kb = easeOut((t - 0.35) / 1.4), kf = easeOut((t - 0.15) / 1.5);
    holder.position.y = 0.05 * Math.sin(t * 0.7);
    holder.rotation.set(0.05 * Math.sin(t * 0.27) + pointer.y * 0.22, -0.62 + 0.2 * Math.sin(t * 0.35) + pointer.x * 0.45, 0);
    fish.parts.body.scale.setScalar(0.85 + 0.15 * k);
    fish.parts.tail.position.x = -90 * (1 - k);
    fish.parts.fin.position.y = 70 * (1 - kf);
    fish.parts.band.position.z = 160 * (1 - kb);
    fish.parts.band.scale.x = 0.2 + 0.8 * kb;
    MAT.orange.emissiveIntensity = 0.4 + 0.12 * Math.sin(t * 1.8);
    spin.rotation.y = -t * 0.1;
    ring.scale.setScalar(0.7 + 0.3 * k);
    spin.children.forEach((c, i) => { if (c.children.length) c.children[0].rotation.y = 0.35 * Math.sin(t * 0.6 + i); });
    const pa = t * 0.8;
    packet.position.set(Math.cos(pa) * R, 0, Math.sin(pa) * R);
    for (const { d, s } of trail) s.position.set(Math.cos(pa - d) * R, 0, Math.sin(pa - d) * R);
    renderer.render(scene, camera);
  };
}

// ---- Scene 2: sensors -> gateway -> central server -> screens, with data packets ----
function iotScene(canvas, section, labels) {
  const { renderer, scene, camera, fit } = stage(canvas, section, 26, 0.8, 0xa8b8c8);
  scene.fog = new Fog(scene.background, 12, 24);
  keyLight(scene, -3, 8, 5, 6, 2048);

  // Floor of rounded tiles, one draw call.
  const tile = new RoundedBoxGeometry(0.47, 0.06, 0.47, 2, 0.015);
  const tiles = new InstancedMesh(tile, new MeshStandardMaterial({ color: 0x17191c, roughness: 0.8, metalness: 0.1 }), 18 * 7);
  const tileB = new Color(0x1d2024), tileA = new Color(0x15171a), d = new Object3D();
  for (let i = 0, n = 0; i < 18; i++) for (let j = 0; j < 7; j++, n++) {
    d.position.set(-4.25 + i * 0.5, -0.03, -1.5 + j * 0.5); d.updateMatrix();
    tiles.setMatrixAt(n, d.matrix); tiles.setColorAt(n, (i + j) % 2 ? tileA : tileB);
  }
  tiles.receiveShadow = true;
  scene.add(tiles);

  const N = { s0: [-3.6, -0.85], s1: [-3.6, 0], s2: [-3.6, 0.85], g: [-1.25, 0], c: [1.25, 0], k0: [3.6, -0.6], k1: [3.6, 0.6] };
  const make = { s0: sensor, s1: radio, s2: meter, g: minipc, c: server, k0: kiosk, k1: kiosk };
  const turn = { k0: -0.35, k1: -0.15, s0: 0.3, s1: 0.2, s2: 0.1 };
  const dev = {};
  for (const k in N) {
    const m = make[k]();
    m.group.position.set(N[k][0], 0, N[k][1]);
    m.group.rotation.y = turn[k] || 0;
    scene.add(m.group);
    dev[k] = m;
  }
  // Cables lying on the floor, and the arcs the packets fly along.
  const LINKS = [["s0", "g"], ["s1", "g"], ["s2", "g"], ["g", "c"], ["c", "k0"], ["c", "k1"]];
  const cableMat = new MeshStandardMaterial({ color: 0x2c3237, roughness: 0.6 });
  const arcs = {};
  for (const [a, b] of LINKS) {
    const A = N[a], B = N[b];
    const mid = new Vector3((A[0] + B[0]) / 2 + (B[1] - A[1]) * 0.08, 0.012, (A[1] + B[1]) / 2);
    const cable = new CatmullRomCurve3([new Vector3(A[0], 0.012, A[1]), mid, new Vector3(B[0], 0.012, B[1])]);
    const m = new Mesh(new TubeGeometry(cable, 40, 0.014, 8, false), cableMat);
    m.receiveShadow = true;
    scene.add(m);
    arcs[a + b] = new QuadraticBezierCurve3(new Vector3(A[0], 0.3, A[1]), new Vector3((A[0] + B[0]) / 2, 0.95, (A[1] + B[1]) / 2), new Vector3(B[0], 0.3, B[1]));
  }
  // Packet timetable, repeating every PERIOD seconds.
  const PERIOD = 3.6, HOPS = [];
  for (let i = 0; i < 3; i++) {
    HOPS.push({ a: "s" + i, b: "g", t0: i * 0.35, d: 0.85 });
    HOPS.push({ a: "g", b: "c", t0: 1.3 + i * 0.3, d: 0.7 });
    HOPS.push({ a: "c", b: "k0", t0: 2.1 + i * 0.3, d: 0.65 });
    HOPS.push({ a: "c", b: "k1", t0: 2.15 + i * 0.3, d: 0.65 });
  }
  const packets = HOPS.map(() => {
    const p = new Group();
    p.add(new Mesh(new SphereGeometry(0.05, 20, 14), MAT.orange), glow(0.55));
    const trail = [0.05, 0.1, 0.16].map((_, i) => { const s = glow(0.36 - i * 0.08); s.material.opacity = 0.5 - i * 0.14; scene.add(s); return s; });
    scene.add(p);
    return { p, trail };
  });
  // A ripple on the floor when a packet arrives.
  const ripples = {};
  for (const k in N) {
    const r = new Mesh(new RingGeometry(0.5, 0.53, 64), new MeshBasicMaterial({ color: ORANGE, transparent: true, depthWrite: false, toneMapped: false }));
    r.rotation.x = -Math.PI / 2; r.position.set(N[k][0], 0.005, N[k][1]);
    scene.add(r); ripples[k] = r;
  }

  let start = null, lastCycle = -1;
  return function render(t, still) {
    fit();
    if (start === null) start = t;
    const tv = still ? 99 : t - start;
    const R = 9.3 * Math.max(1, 2.1 / camera.aspect), a = -0.42 + 0.06 * Math.sin(t * 0.12);
    camera.position.set(Math.sin(a) * R, R * 0.58, Math.cos(a) * R);
    camera.lookAt(0, 0.3, 0);
    scene.fog.near = R + 1; scene.fog.far = R + 12;

    const cyc = t % PERIOD, cycle = Math.floor(t / PERIOD), since = {};
    for (const h of HOPS) {
      let dt = cyc - (h.t0 + h.d); if (dt < 0) dt += PERIOD;
      since[h.b] = Math.min(since[h.b] ?? 9, dt);
      let dl = cyc - h.t0; if (dl < 0) dl += PERIOD;
      since[h.a] = Math.min(since[h.a] ?? 9, dl);
    }
    Object.keys(N).forEach((k, i) => {
      const rise = easeOut((tv - 0.12 * i) / 0.9);
      dev[k].group.position.y = -1.2 * (1 - rise);
      const pulse = still ? 0.3 : Math.exp(-5 * (since[k] ?? 9));
      for (const l of dev[k].leds) { l.userData.halo.material.opacity = 0.25 + 0.75 * pulse; l.userData.halo.scale.setScalar(0.12 + 0.18 * pulse); }
      const rp = ripples[k], age = still ? 9 : since[k] ?? 9;
      rp.visible = age < 0.9 && tv > 1.2;
      rp.scale.setScalar(0.5 + age * 1.4); rp.material.opacity = 0.6 * (1 - age / 0.9);
    });
    if (cycle !== lastCycle) { dev.k0.draw(cycle % 50, 0); dev.k1.draw((cycle + 17) % 50, 0); lastCycle = cycle; }
    HOPS.forEach((h, i) => {
      let u = cyc - h.t0; if (u < 0) u += PERIOD;
      u /= h.d;
      const { p, trail } = packets[i], on = u <= 1 && tv > 1.2 && !still;
      p.visible = on; trail.forEach((s) => (s.visible = on));
      if (!on) return;
      const arc = arcs[h.a + h.b], e = easeInOut(u);
      arc.getPoint(e, p.position);
      trail.forEach((s, j) => arc.getPoint(easeInOut(clamp(u - (j + 1) * 0.06, 0, 1)), s.position));
    });
    for (const l of labels) {
      const p = N[l.dataset.at], v = new Vector3(p[0], +l.dataset.h, p[1]).project(camera);
      const x = (v.x * 0.5 + 0.5) * canvas.clientWidth, y = (0.5 - v.y * 0.5) * canvas.clientHeight;
      l.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(-50%,-100%)";
      l.style.opacity = clamp((tv - 0.6) / 0.6, 0, 1);
    }
    renderer.render(scene, camera);
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

if (scenes.length) {
  const t0 = performance.now();
  let raf = 0;
  const tick = (now) => {
    raf = 0;
    const t = (now - t0) / 1000;
    let any = false;
    for (const s of scenes) if (s.visible) { s.render(t); any = true; }
    if (any) raf = requestAnimationFrame(tick);
  };
  if (reduce) {
    const still = () => { for (const s of scenes) s.render(30, true); };
    still();
    addEventListener("resize", still);
  } else {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) { const s = scenes.find((x) => x.el === e.target); if (s) s.visible = e.isIntersecting; }
      if (!raf && scenes.some((s) => s.visible)) raf = requestAnimationFrame(tick);
    });
    scenes.forEach((s) => io.observe(s.el));
  }
}
