// Models of the website's 3D scenes, built in code (no model files to
// download): the logo trout and the devices Trota OS runs on. Units are
// metres-ish; every device stands on y = 0 and faces +z.
import {
  AdditiveBlending, CanvasTexture, CylinderGeometry, ExtrudeGeometry, Group, Mesh, MeshBasicMaterial,
  MeshPhysicalMaterial, MeshStandardMaterial, PlaneGeometry, Shape, Path, SphereGeometry, Sprite,
  SpriteMaterial, SRGBColorSpace,
} from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

export const ORANGE = 0xff6a2a;

export const MAT = {
  shell: new MeshPhysicalMaterial({ color: 0xd6dbe0, roughness: 0.34, clearcoat: 0.6, clearcoatRoughness: 0.25 }),
  shell2: new MeshPhysicalMaterial({ color: 0xc3c9cf, roughness: 0.4, clearcoat: 0.4, clearcoatRoughness: 0.3 }),
  alu: new MeshStandardMaterial({ color: 0xb9c0c7, roughness: 0.3, metalness: 0.8 }),
  steel: new MeshStandardMaterial({ color: 0x7d858d, roughness: 0.42, metalness: 0.7 }),
  dark: new MeshStandardMaterial({ color: 0x1c1f23, roughness: 0.55, metalness: 0.2 }),
  vent: new MeshStandardMaterial({ color: 0x2a2f35, roughness: 0.7 }),
  glass: new MeshPhysicalMaterial({ color: 0x0b0c0e, roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.05 }),
  orange: new MeshPhysicalMaterial({ color: ORANGE, emissive: ORANGE, emissiveIntensity: 0.45, roughness: 0.32, clearcoat: 0.7 }),
  led: new MeshBasicMaterial({ color: 0xff8a4d, toneMapped: false }),
};

function mesh(geo, mat, shadow = true) {
  const m = new Mesh(geo, mat);
  m.castShadow = shadow; m.receiveShadow = shadow;
  return m;
}
const at = (obj, x, y, z) => { obj.position.set(x, y, z); return obj; };
export const rbox = (w, h, d, r, mat) => mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2, h / 2, d / 2)), mat);
const cyl = (rt, rb, h, mat, seg = 32) => mesh(new CylinderGeometry(rt, rb, h, seg), mat);

// A soft additive glow, for LEDs and data packets.
let glowTex;
export function glow(scale = 0.3, color = ORANGE) {
  if (!glowTex) {
    const c = document.createElement("canvas"); c.width = c.height = 64;
    const g = c.getContext("2d"), grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(0.25, "rgba(255,255,255,0.45)"); grd.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
    glowTex = new CanvasTexture(c); glowTex.colorSpace = SRGBColorSpace;
  }
  const s = new Sprite(new SpriteMaterial({ map: glowTex, color, blending: AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false }));
  s.scale.setScalar(scale);
  return s;
}

// An LED: a small bright bead with its glow. `led.userData.glow` is driven by the scene.
function led(x, y, z, r = 0.014) {
  const g = at(new Group(), x, y, z);
  g.add(mesh(new SphereGeometry(r, 12, 8), MAT.led, false));
  const halo = glow(r * 14); g.add(halo);
  g.userData.halo = halo;
  return g;
}

// ---- The logo trout (256-unit grid of trota-symbol.svg, y down) ----
const toShape = (pts) => {
  const s = new Shape();
  pts.forEach(([x, y], i) => (i ? s.lineTo(x - 128, 128 - y) : s.moveTo(x - 128, 128 - y)));
  s.closePath();
  return s;
};
const toPath = (pts) => {
  const p = new Path();
  pts.forEach(([x, y], i) => (i ? p.lineTo(x - 128, 128 - y) : p.moveTo(x - 128, 128 - y)));
  p.closePath();
  return p;
};
function extrude(shape, depth, bevel, mat) {
  const geo = new ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel * 0.8, bevelSegments: 4, curveSegments: 1 });
  geo.translate(0, 0, -depth / 2);
  return mesh(geo, mat);
}
const EYE = [[206, 112], [214, 112], [214, 120], [206, 120]];
const GILL = [[180, 101], [185, 101], [194, 128], [185, 155], [180, 155], [189, 128]];

// Returns { group, parts: { tail, body, fin, band } } in logo units (scale it down).
export function trout() {
  const group = new Group();
  const body = toShape([[60, 128], [102, 94], [198, 94], [238, 128], [198, 162], [102, 162]]);
  body.holes.push(toPath(EYE), toPath(GILL));
  const parts = {
    tail: extrude(toShape([[52, 128], [16, 98], [28, 128], [16, 158]]), 16, 3, MAT.shell2),
    body: extrude(body, 16, 3, MAT.shell),
    fin: extrude(toShape([[124, 94], [142, 76], [174, 76], [164, 94]]), 14, 3, MAT.shell2),
    // The lateral line, split where the gill crosses it, as in the logo.
    band: new Group(),
  };
  parts.band.add(extrude(toShape([[88, 123], [187.33, 123], [189, 128], [187.33, 133], [88, 133], [83, 128]]), 22, 2.5, MAT.orange));
  parts.band.add(extrude(toShape([[192.33, 123], [214, 123], [219, 128], [214, 133], [192.33, 133], [194, 128]]), 22, 2.5, MAT.orange));
  // Dark cores inside the eye and gill cut-outs: the holes read as real depth.
  const core = new Group();
  core.add(extrude(toShape(EYE), 12, 0.5, MAT.glass), extrude(toShape(GILL), 12, 0.5, MAT.glass));
  parts.body.add(core);
  group.add(parts.tail, parts.body, parts.fin, parts.band);
  return { group, parts };
}

// ---- Devices ----
export function laptop() {
  const g = new Group(), leds = [];
  g.add(at(rbox(0.9, 0.045, 0.62, 0.02, MAT.alu), 0, 0.0225, 0));
  g.add(at(rbox(0.78, 0.008, 0.3, 0.004, MAT.dark), 0, 0.045, -0.06));
  g.add(at(rbox(0.26, 0.006, 0.15, 0.004, MAT.steel), 0, 0.045, 0.19));
  const lid = at(new Group(), 0, 0.045, -0.295);
  lid.rotation.x = -0.28;
  lid.add(at(rbox(0.9, 0.6, 0.028, 0.02, MAT.alu), 0, 0.3, 0));
  lid.add(at(rbox(0.84, 0.53, 0.006, 0.004, MAT.glass), 0, 0.31, 0.014));
  lid.add(at(rbox(0.36, 0.035, 0.006, 0.006, MAT.orange), -0.08, 0.31, 0.017));
  g.add(lid);
  return { group: g, leds, height: 0.62 };
}

export function server() {
  const g = new Group(), leds = [];
  g.add(at(rbox(1.0, 0.06, 0.8, 0.02, MAT.dark), 0, 0.03, 0));
  for (let i = 0; i < 3; i++) {
    const y = 0.175 + i * 0.24;
    g.add(at(rbox(0.95, 0.21, 0.72, 0.03, i === 1 ? MAT.shell : MAT.alu), 0, y, 0));
    g.add(at(rbox(0.52, 0.12, 0.012, 0.006, MAT.dark), -0.16, y, 0.36));
    for (let k = 0; k < 8; k++) g.add(at(rbox(0.014, 0.085, 0.008, 0.004, MAT.vent), -0.38 + k * 0.063, y, 0.368));
    g.add(at(rbox(0.17, 0.045, 0.012, 0.006, MAT.steel), 0.25, y + 0.03, 0.36));
    g.add(at(rbox(0.17, 0.045, 0.012, 0.006, MAT.steel), 0.25, y - 0.03, 0.36));
    const l = led(0.41, y, 0.368); g.add(l); leds.push(l);
  }
  return { group: g, leds, height: 0.83 };
}

export function minipc() {
  const g = new Group(), leds = [];
  g.add(at(rbox(0.95, 0.28, 0.75, 0.08, MAT.shell), 0, 0.15, 0));
  g.add(at(rbox(0.64, 0.012, 0.48, 0.006, MAT.alu), 0, 0.29, 0));
  for (let k = 0; k < 7; k++) g.add(at(rbox(0.5, 0.008, 0.016, 0.004, MAT.vent), 0, 0.295, -0.18 + k * 0.06));
  g.add(at(rbox(0.46, 0.024, 0.012, 0.01, MAT.orange), -0.12, 0.11, 0.375));
  for (let k = 0; k < 2; k++) g.add(at(rbox(0.06, 0.032, 0.012, 0.005, MAT.glass), 0.22 + k * 0.08, 0.16, 0.375));
  for (const [x, z] of [[-0.4, -0.3], [0.4, -0.3], [-0.4, 0.3], [0.4, 0.3]]) g.add(at(cyl(0.04, 0.04, 0.012, MAT.dark, 16), x, 0.006, z));
  const l = led(0.38, 0.1, 0.38); g.add(l); leds.push(l);
  return { group: g, leds, height: 0.3 };
}

export function sensor() {
  const g = new Group(), leds = [];
  g.add(at(cyl(0.2, 0.22, 0.05, MAT.steel), 0, 0.025, 0));
  g.add(at(cyl(0.14, 0.14, 0.3, MAT.shell), 0, 0.2, 0));
  g.add(at(mesh(new SphereGeometry(0.14, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2), MAT.shell), 0, 0.35, 0));
  for (const y of [0.12, 0.16, 0.2]) g.add(at(cyl(0.143, 0.143, 0.012, MAT.vent), 0, y, 0));
  const l = led(0, 0.28, 0.142); g.add(l); leds.push(l);
  return { group: g, leds, height: 0.5 };
}

export function radio() {
  const g = new Group(), leds = [];
  g.add(at(rbox(0.42, 0.28, 0.28, 0.07, MAT.alu), 0, 0.14, 0));
  g.add(at(rbox(0.2, 0.08, 0.012, 0.01, MAT.dark), -0.06, 0.15, 0.14));
  g.add(at(cyl(0.014, 0.014, 0.32, MAT.steel, 12), 0.13, 0.44, -0.06));
  g.add(at(mesh(new SphereGeometry(0.032, 16, 12), MAT.dark), 0.13, 0.6, -0.06));
  const l = led(0.12, 0.15, 0.142); g.add(l); leds.push(l);
  return { group: g, leds, height: 0.64 };
}

export function meter() {
  const g = new Group(), leds = [];
  g.add(at(rbox(0.42, 0.48, 0.24, 0.035, MAT.shell), 0, 0.24, 0));
  g.add(at(rbox(0.3, 0.12, 0.014, 0.01, MAT.glass), 0, 0.33, 0.12));
  g.add(at(rbox(0.16, 0.034, 0.006, 0.006, MAT.orange), -0.04, 0.33, 0.128));
  for (let k = 0; k < 4; k++) g.add(at(rbox(0.06, 0.06, 0.014, 0.01, MAT.dark), -0.135 + k * 0.09, 0.09, 0.12));
  const l = led(0.13, 0.43, 0.122); g.add(l); leds.push(l);
  return { group: g, leds, height: 0.48 };
}

// A screen showing a live dashboard: `draw(state)` repaints it.
export function kiosk() {
  const g = new Group(), leds = [];
  const c = document.createElement("canvas"); c.width = 512; c.height = 300;
  const tex = new CanvasTexture(c); tex.colorSpace = SRGBColorSpace; tex.anisotropy = 4;
  g.add(at(rbox(0.46, 0.035, 0.3, 0.015, MAT.alu), 0, 0.0175, 0));
  g.add(at(cyl(0.028, 0.034, 0.56, MAT.alu, 16), 0, 0.3, -0.05));
  const head = at(new Group(), 0, 0.86, 0);
  head.rotation.x = -0.08;
  head.add(at(rbox(0.9, 0.56, 0.06, 0.03, MAT.alu), 0, 0, -0.03));
  head.add(at(rbox(0.98, 0.62, 0.03, 0.025, MAT.dark), 0, 0, 0.01));
  const screen = mesh(new PlaneGeometry(0.9, 0.54), new MeshStandardMaterial({ map: tex, emissiveMap: tex, emissive: 0xffffff, emissiveIntensity: 0.85, roughness: 0.25 }), false);
  head.add(at(screen, 0, 0, 0.026));
  const l = led(0.44, -0.28, 0.026, 0.01); head.add(l); leds.push(l);
  g.add(head);
  const ctx = c.getContext("2d");
  function draw(seed, bump) {
    ctx.fillStyle = "#0B0C0E"; ctx.fillRect(0, 0, 512, 300);
    ctx.fillStyle = "#9AA2AA"; ctx.font = "500 20px 'IBM Plex Mono', monospace"; ctx.fillText("REPARTO 2 · OGGI", 28, 44);
    ctx.fillStyle = "#E8ECEF"; ctx.font = "300 62px 'IBM Plex Sans', sans-serif"; ctx.fillText((1240 + seed * 7).toLocaleString("it-IT"), 26, 116);
    ctx.fillStyle = "#FF6A2A"; ctx.font = "500 20px 'IBM Plex Mono', monospace"; ctx.fillText("pezzi", 30, 148);
    for (let i = 0; i < 7; i++) {
      const h = 40 + ((i * 37 + seed * 13) % 70) + (i === 6 ? bump * 40 : 0);
      ctx.fillStyle = i === 6 ? "#FF6A2A" : "#5A626A";
      ctx.fillRect(28 + i * 34, 272 - h, 22, h);
    }
    ctx.strokeStyle = "#FF6A2A"; ctx.lineWidth = 4; ctx.beginPath();
    for (let i = 0; i < 8; i++) {
      const x = 300 + i * 26, y = 250 - 20 * i - 18 * Math.sin(i * 1.3 + seed);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();
    tex.needsUpdate = true;
  }
  draw(0, 0);
  return { group: g, leds, height: 1.17, draw };
}

export function cloud() {
  const g = new Group();
  for (const [x, y, r] of [[0, 0.3, 0.22], [-0.24, 0.2, 0.16], [0.24, 0.19, 0.15], [0.08, 0.44, 0.15], [-0.1, 0.12, 0.13], [0.12, 0.12, 0.12]])
    g.add(at(mesh(new SphereGeometry(r, 32, 16), MAT.shell), x, y, 0));
  return { group: g, leds: [], height: 0.6 };
}
