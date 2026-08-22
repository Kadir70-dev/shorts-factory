/** Reusable single-browser worker for deterministic finance visual frames. */
import {createInterface} from "node:readline";
import {mkdir, writeFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {dirname, join} from "node:path";
import {tmpdir} from "node:os";
import {execFileSync} from "node:child_process";
import {pathToFileURL} from "node:url";
import puppeteer, {Browser, Page} from "puppeteer";

type Template = "number_counter" | "comparison_towers" | "share_ownership" |
  "dividend_cashflow" | "timeline_flythrough" | "compound_growth" | "globe_flight";
/** lon/lat ring, as delivered by pipeline/geo_data.py. */
type Ring = ReadonlyArray<readonly [number, number]>;
/** One leg of the camera flight: where it arrives and how tight it gets. */
type Waypoint = {readonly lon: number; readonly lat: number; readonly altitude: number;
                 readonly hold: number};
/** A country/state painted proud of the base map, with its own screen label. */
type Region = {readonly rings: readonly Ring[]; readonly label: string;
               readonly lon: number; readonly lat: number;
               readonly tone: "primary" | "secondary"};
/** The currency leg travelling between two regions. */
type Route = {readonly from: readonly [number, number];
              readonly to: readonly [number, number];
              readonly fromLabel: string; readonly toLabel: string};
type Request = {
  id: string; outputDir: string; template: Template; width: number; height: number;
  fps: 30 | 60; frames: number; seed: number; title: string; label: string;
  values: number[]; labels: string[]; palette: Record<string, string>; fontFamily: string;
  // globe_flight only; absent for every existing template.
  world?: readonly Ring[]; highlight?: readonly Ring[]; focus?: readonly Ring[];
  flight?: readonly Waypoint[]; pins?: ReadonlyArray<{readonly lon: number;
    readonly lat: number; readonly label: string}>;
  regions?: readonly Region[]; route?: Route;
  /** globe_flight renderer. "2d" = canvas orthographic globe (fast, crisp);
   *  "3d" = textured WebGL sphere. Defaults to 3d for callers that omit it. */
  mode?: "2d" | "3d";
};

let browser: Browser | null = null;
let page: Page | null = null;

function aggregateRssMb(): number {
  let kb = process.memoryUsage().rss / 1024;
  const root = browser?.process()?.pid;
  if (!root) return kb / 1024;
  try {
    const rows = execFileSync("ps", ["-e", "-o", "pid=,ppid=,rss="],
                              {encoding: "utf8"}).trim().split("\n").map(line => {
      const [pid, ppid, rss] = line.trim().split(/\s+/).map(Number);
      return {pid, ppid, rss};
    });
    const family = new Set<number>([root]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const row of rows) if (family.has(row.ppid) && !family.has(row.pid)) {
        family.add(row.pid); changed = true;
      }
    }
    kb += rows.filter(row => family.has(row.pid)).reduce((sum, row) => sum + row.rss, 0);
  } catch { /* RSS remains the conservative Node-process measurement. */ }
  return kb / 1024;
}

async function ensurePage(req: Request): Promise<Page> {
  if (!browser) {
    browser = await puppeteer.launch({
      headless: true,
      executablePath: process.env.THREEJS_BROWSER_EXECUTABLE || undefined,
      args: ["--disable-dev-shm-usage", "--no-sandbox", "--use-gl=swiftshader",
             "--enable-unsafe-swiftshader", "--allow-file-access-from-files",
             "--js-flags=--max-old-space-size=384"],
    });
  }
  if (!page) {
    page = await browser.newPage();
    const require = createRequire(import.meta.url);
    const threeUrl = pathToFileURL(join(dirname(require.resolve("three")),
                                        "three.module.min.js")).href;
    const htmlPath = join(tmpdir(), "shorts-factory-threejs-worker.html");
    await writeFile(htmlPath, `<!doctype html><html><body style="margin:0;overflow:hidden;background:#000">
      <script type="module">import * as THREE from '${threeUrl}'; window.THREE=THREE; window.ready=true;</script>
    </body></html>`);
    await page.goto(pathToFileURL(htmlPath).href, {waitUntil: "load"});
    await page.waitForFunction("window.ready === true");
  }
  await page.setViewport({width: req.width, height: req.height, deviceScaleFactor: 1});
  return page;
}

/** Canvas-2D orthographic globe. Software WebGL needs ~700ms/frame at 540x960,
 *  which puts a 6-second beat past the worker timeout; the same geometry drawn
 *  with the 2D context lands in tens of milliseconds and is SHARPER, because
 *  strokes and fills are rasterised at output resolution instead of being
 *  upscaled from a preview-sized framebuffer. */
async function renderFlat(p: Page, req: Request, frame: number): Promise<void> {
  await p.evaluate((input, currentFrame) => {
    document.body.innerHTML = "";
    const canvas = document.createElement("canvas");
    canvas.width = input.width; canvas.height = input.height;
    document.body.appendChild(canvas);
    const g = canvas.getContext("2d");
    if (!g) return;
    const W = input.width, H = input.height;
    const palette = input.palette;
    const primary = palette.primary || "#f5b301";
    const secondary = palette.secondary || "#3d7bfd";
    const ink = palette.ink || "#f4f6fb";
    const progress = input.frames <= 1 ? 1 : currentFrame / (input.frames - 1);

    const legs = input.flight ?? [];
    const weights = legs.map(w => Math.max(.05, w.hold));
    const total = weights.reduce((a, b) => a + b, 0) || 1;
    let travelled = progress * total, index = 0;
    while (index < legs.length - 1 && travelled > weights[index]) {
      travelled -= weights[index]; index += 1;
    }
    const from = legs[Math.max(0, index - 1)] ?? legs[0];
    const to = legs[index] ?? legs[0];
    const legT = Math.min(1, travelled / Math.max(.05, weights[index]));
    const smooth = legT * legT * (3 - 2 * legT);
    let dLon = to.lon - from.lon;
    if (dLon > 180) dLon -= 360; if (dLon < -180) dLon += 360;
    const lon0 = from.lon + dLon * smooth;
    const lat0 = from.lat + (to.lat - from.lat) * smooth;
    const altitude = from.altitude + (to.altitude - from.altitude) * smooth;

    // Globe radius in pixels: the whole disc fits the frame at cruising
    // altitude and overflows it on the close legs, which IS the zoom.
    const radius = Math.min(W, H) * (0.46 * 4.3 / Math.max(1.0, altitude));
    const cx = W / 2, cy = H * 0.43;               // above the caption band
    const rad = Math.PI / 180;
    const cosLat0 = Math.cos(lat0 * rad), sinLat0 = Math.sin(lat0 * rad);
    // Orthographic: visible only where the surface faces the camera (cosc > 0).
    const project = (lon: number, lat: number): [number, number, number] => {
      const dl = (lon - lon0) * rad, la = lat * rad;
      const cosc = sinLat0 * Math.sin(la) + cosLat0 * Math.cos(la) * Math.cos(dl);
      const x = cx + radius * Math.cos(la) * Math.sin(dl);
      const y = cy - radius * (cosLat0 * Math.sin(la) - sinLat0 * Math.cos(la) * Math.cos(dl));
      return [x, y, cosc];
    };
    const tracePath = (ring: ReadonlyArray<readonly [number, number]>): boolean => {
      let started = false, drawn = false;
      g.beginPath();
      for (const [lo, la] of ring) {
        const [x, y, cosc] = project(lo, la);
        if (cosc <= 0) { started = false; continue; }   // behind the horizon
        if (!started) { g.moveTo(x, y); started = true; } else { g.lineTo(x, y); }
        drawn = true;
      }
      return drawn;
    };

    g.fillStyle = palette.bg || "#0b1220";
    g.fillRect(0, 0, W, H);
    // Ocean disc + rim light, so the planet reads as a sphere and not a decal.
    const sphere = g.createRadialGradient(cx - radius * .3, cy - radius * .35,
                                          radius * .1, cx, cy, radius);
    sphere.addColorStop(0, palette.bg_soft || "#16233c");
    sphere.addColorStop(1, palette.bg || "#0b1220");
    g.beginPath(); g.arc(cx, cy, radius, 0, Math.PI * 2);
    g.fillStyle = sphere; g.fill();
    g.lineWidth = Math.max(2, radius * .012); g.strokeStyle = secondary;
    g.globalAlpha = .5; g.stroke(); g.globalAlpha = 1;

    g.save();
    g.beginPath(); g.arc(cx, cy, radius, 0, Math.PI * 2); g.clip();
    const land = palette.bg_soft ? "#233350" : "#233350";
    for (const ring of input.world ?? []) {
      if (tracePath(ring)) { g.closePath(); g.fillStyle = land; g.fill(); }
    }
    g.lineWidth = Math.max(1.2, radius * .0035);
    g.strokeStyle = palette.grid || "#445a7d";
    g.lineJoin = "round";
    for (const ring of input.world ?? []) { if (tracePath(ring)) g.stroke(); }
    for (const region of input.regions ?? []) {
      const tone = region.tone === "primary" ? primary : secondary;
      for (const ring of region.rings) {
        if (tracePath(ring)) { g.closePath(); g.fillStyle = tone; g.fill(); }
      }
      g.strokeStyle = ink; g.lineWidth = Math.max(2, radius * .008);
      for (const ring of region.rings) { if (tracePath(ring)) g.stroke(); }
    }

    // ROUTE — a great-circle arc that draws itself, with the money on it.
    const geo = input.route;
    if (geo) {
      const toXYZ = (lon: number, lat: number) => {
        const la = lat * rad, lo = lon * rad;
        return [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)];
      };
      const a = toXYZ(geo.from[0], geo.from[1]), b = toXYZ(geo.to[0], geo.to[1]);
      const arcAt = (t: number): [number, number] => {
        const v = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
        const n = Math.hypot(v[0], v[1], v[2]) || 1;
        const lat = Math.asin(v[2] / n) / rad;
        const lon = Math.atan2(v[1] / n, v[0] / n) / rad;
        // Bow the route poleward. A true great circle between two mid-latitude
        // points is nearly edge-on in this projection and reads as a straight
        // line; the bulge is what makes it look like a route on a globe. Costs
        // nothing — it is the same 72 samples, displaced.
        return [lon, lat + 11 * Math.sin(Math.PI * t)];
      };
      const drawn = Math.max(.001, Math.min(1, (progress - .30) / .44));
      g.beginPath();
      let open = false;
      for (let i = 0; i <= 72; i++) {
        const [lo, la] = arcAt(drawn * i / 72);
        const [x, y, cosc] = project(lo, la);
        if (cosc <= 0) { open = false; continue; }
        if (!open) { g.moveTo(x, y); open = true; } else { g.lineTo(x, y); }
      }
      g.strokeStyle = primary; g.lineWidth = Math.max(4, radius * .016);
      g.lineCap = "round";
      g.shadowColor = primary; g.shadowBlur = radius * .05;
      g.stroke();
      g.shadowBlur = 0;
      const [hlo, hla] = arcAt(drawn);
      const [hx, hy, hcos] = project(hlo, hla);
      if (hcos > 0) {
        g.beginPath(); g.arc(hx, hy, Math.max(6, radius * .026), 0, Math.PI * 2);
        g.fillStyle = ink; g.fill();
        g.beginPath(); g.arc(hx, hy, Math.max(12, radius * .05), 0, Math.PI * 2);
        g.fillStyle = primary; g.globalAlpha = .35; g.fill(); g.globalAlpha = 1;
      }
    }
    g.restore();

    // Region labels, drawn OUTSIDE the clip so they are never cut by the limb.
    for (const region of input.regions ?? []) {
      const [x, y, cosc] = project(region.lon, region.lat);
      if (cosc <= .12) continue;
      const size = Math.max(34, Math.min(H * .062, radius * .17));
      g.font = `900 ${size}px ${input.fontFamily}, Arial, sans-serif`;
      g.textAlign = "center"; g.textBaseline = "middle";
      const label = region.label;
      const padX = size * .42, padY = size * .30;
      const w = g.measureText(label).width + padX * 2;
      // Clamp inside the frame. A label anchored to a country near the limb ran
      // off the edge and rendered as "EU", which is worse than not labelling it.
      const margin = W * .04;
      const lx = Math.max(w / 2 + margin, Math.min(W - w / 2 - margin, x));
      const ly = Math.max(size * 1.4,
                          Math.min(H * .70, y - radius * .10 - size));
      g.globalAlpha = Math.min(1, (cosc - .12) * 5);
      g.fillStyle = palette.bg || "#0b1220";
      g.globalAlpha *= .82;
      g.fillRect(lx - w / 2, ly - size / 2 - padY, w, size + padY * 2);
      g.globalAlpha = Math.min(1, (cosc - .12) * 5);
      g.fillStyle = region.tone === "primary" ? primary : secondary;
      g.fillRect(lx - w / 2, ly + size / 2 + padY - Math.max(3, size * .06), w,
                 Math.max(3, size * .06));
      g.fillStyle = ink;
      g.fillText(label, lx, ly);
      g.globalAlpha = 1;
      g.beginPath(); g.arc(x, y, Math.max(4, radius * .016), 0, Math.PI * 2);
      g.fillStyle = ink; g.fill();
      g.beginPath(); g.moveTo(lx, ly + size / 2 + padY); g.lineTo(x, y);
      g.strokeStyle = ink; g.globalAlpha = .35;
      g.lineWidth = Math.max(1.5, radius * .004); g.stroke(); g.globalAlpha = 1;
    }
  }, req, frame);
}

async function renderFrame(p: Page, req: Request, frame: number): Promise<void> {
  if (req.template === "globe_flight" && req.mode !== "3d") {
    await renderFlat(p, req, frame);
    return;
  }
  await p.evaluate((input, currentFrame) => {
    const T = (window as any).THREE;
    document.body.innerHTML = "";
    const canvas = document.createElement("canvas");
    canvas.width = input.width; canvas.height = input.height;
    document.body.appendChild(canvas);
    const renderer = new T.WebGLRenderer({canvas, antialias: false, alpha: false,
                                          powerPreference: "low-power"});
    renderer.setSize(input.width, input.height, false);
    renderer.setPixelRatio(1);
    const scene = new T.Scene();
    scene.background = new T.Color(input.palette.bg || "#0b1220");
    const camera = new T.PerspectiveCamera(42, input.width / input.height, .1, 100);
    camera.position.set(0, 0, 12);
    const progress = input.frames <= 1 ? 1 : currentFrame / (input.frames - 1);
    const ease = 1 - Math.pow(1 - progress, 3);
    const rand = (n: number) => {
      const x = Math.sin(input.seed * 12.9898 + n * 78.233) * 43758.5453;
      return x - Math.floor(x);
    };
    scene.add(new T.AmbientLight(0xffffff, 2.1));
    const key = new T.DirectionalLight(0xffffff, 3.2); key.position.set(4, 8, 9); scene.add(key);
    const mat = (color: string, opacity = 1) => new T.MeshStandardMaterial({
      color, roughness: .55, metalness: .18, transparent: opacity < 1, opacity});
    const box = (x: number, y: number, w: number, h: number, color: string, z = 0) => {
      const mesh = new T.Mesh(new T.BoxGeometry(w, h, .55), mat(color));
      mesh.position.set(x, y, z); scene.add(mesh); return mesh;
    };
    const line = (points: Array<[number, number, number]>, color: string) => {
      const geo = new T.BufferGeometry().setFromPoints(points.map(v => new T.Vector3(...v)));
      scene.add(new T.Line(geo, new T.LineBasicMaterial({color, linewidth: 5})));
    };
    // World-space extent actually visible at the subject plane (z=0). Everything
    // below is sized against this instead of hard-coded numbers: the templates
    // were authored for a landscape frame, and at 9:16 the visible width is only
    // ~5.2 units, so bars at x=+/-2.975 and 9.2-unit text sprites rendered off
    // the edge of the frame.
    const visibleH = 2 * camera.position.z * Math.tan((42 * Math.PI / 180) / 2);
    const visibleW = visibleH * (input.width / input.height);
    const safeW = visibleW * 0.92;

    const text = (value: string, y: number, size: number, color: string, x = 0,
                  widthUnits = safeW) => {
      const c = document.createElement("canvas"); c.width = 1536; c.height = 320;
      const ctx = c.getContext("2d")!; ctx.clearRect(0, 0, c.width, c.height);
      // The sprite is narrower than the old fixed 9.2 units, so a glyph drawn at
      // `size` would appear proportionally smaller on screen. Scaling the font by
      // the same ratio keeps apparent type size unchanged while the sprite fits.
      const scaled = size * (9.2 / widthUnits);
      ctx.fillStyle = color; ctx.font = `900 ${scaled}px ${input.fontFamily}, Arial, sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(value, 768, 160, 1450);
      const texture = new T.CanvasTexture(c); texture.colorSpace = T.SRGBColorSpace;
      const sprite = new T.Sprite(new T.SpriteMaterial({map: texture, transparent: true}));
      sprite.scale.set(widthUnits, widthUnits / 4.8, 1);
      sprite.position.set(x, y, 1.8); scene.add(sprite);
    };
    const primary = input.palette.primary || "#f5b301";
    const secondary = input.palette.secondary || "#3d7bfd";
    const positive = input.palette.positive || "#16c784";
    const ink = input.palette.ink || "#f4f6fb";
    text(input.title.toUpperCase(), 4.25, 94, ink);

    if (input.template === "number_counter") {
      const value = (input.values[0] || 0) * ease;
      const ring = new T.Mesh(new T.TorusGeometry(2.7, .18, 16, 80, Math.PI * 2 * ease), mat(primary));
      ring.rotation.z = Math.PI / 2; scene.add(ring);
      text(Math.abs(value) >= 1e9 ? `$${(value / 1e9).toFixed(1)}B` : value.toLocaleString("en-US", {maximumFractionDigits: 1}), 0, 156, primary);
      text(input.label, -2.1, 72, ink);
    } else if (input.template === "comparison_towers") {
      // Was hard-limited to slice(0, 2): a five-category series silently lost
      // three bars while `max` was still computed across all five, so the chart
      // showed two towers scaled against data the viewer could not see.
      const vals = input.values.slice(0, 6);
      const n = Math.max(1, vals.length);
      const max = Math.max(...vals, 1);
      const gap = n > 1 ? safeW * 0.05 / (n - 1) : 0;
      const barW = (safeW * 0.88 - gap * (n - 1)) / n;
      const left = -(safeW * 0.88) / 2 + barW / 2;
      vals.forEach((v: number, i: number) => {
        const h = 5.0 * v / max * ease;
        const x = left + i * (barW + gap);
        box(x, -2.4 + h / 2, barW * 0.92, h, i === 0 ? primary : secondary);
        // Label sprite is bar-width bound so adjacent labels cannot overlap.
        text(String(input.labels[i] ?? v), -3.15, 54, ink, x,
             Math.min(safeW, barW * 1.55));
      });
    } else if (input.template === "share_ownership") {
      const total = input.values.reduce((a: number, b: number) => a + b, 0) || 100;
      let start = 0;
      input.values.forEach((v: number, i: number) => {
        const angle = Math.PI * 2 * v / total * ease;
        const geo = new T.RingGeometry(1.75, 3.1, 64, 1, start, angle);
        scene.add(new T.Mesh(geo, mat([primary, secondary, positive, input.palette.negative || "#ea3943"][i % 4])));
        start += Math.PI * 2 * v / total;
      });
      text(`${Math.round((input.values[0] || 0) / total * 100)}%`, 0, 150, ink);
      text(input.label, -3.25, 66, ink);
    } else if (input.template === "dividend_cashflow") {
      box(-3.25, 0, 1.4, 4.8, secondary); box(3.25, 0, 1.4, 4.8, positive);
      for (let i = 0; i < 18; i++) {
        const x = -2.5 + ((progress * 1.4 + i / 18 + rand(i) * .1) % 1) * 5;
        const coin = new T.Mesh(new T.CylinderGeometry(.22, .22, .08, 16), mat(primary));
        coin.rotation.x = Math.PI / 2; coin.position.set(x, Math.sin(i * 2.1) * 1.4, .5); scene.add(coin);
      }
      text(input.label || "DIVIDEND CASH FLOW", -3.25, 66, ink);
    } else if (input.template === "timeline_flythrough") {
      camera.position.z = 12 - progress * 5; camera.position.x = Math.sin(progress * Math.PI) * .7;
      line([[-3.8, 0, 0], [3.8, 0, -4]], primary);
      input.labels.slice(0, 5).forEach((label: string, i: number) => {
        const x = -3.5 + i * 1.75; const z = -i;
        const node = new T.Mesh(new T.SphereGeometry(.28, 16, 16), mat(i <= progress * 5 ? primary : secondary));
        node.position.set(x, 0, z); scene.add(node);
        text(label, i % 2 ? -1.8 : 1.8, 52, ink, x);
      });
    } else if (input.template === "globe_flight") {
      // The map is drawn ONCE into a high-resolution equirectangular canvas and
      // used as the sphere's texture, rather than as WebGL line geometry.
      //
      // Two reasons, both visible in the first cut of this template: WebGL
      // ignores `LineBasicMaterial.linewidth` on every desktop driver, so every
      // border rendered as a 1px hairline that upscaling turned to mush; and
      // outlines alone gave land and ocean the same value, so nothing read as a
      // landmass. A canvas gives real fills, strokes of any width, and stays
      // crisp because the texture is far denser than the output frame.
      const R = 3.0;
      const toVec = (lon: number, lat: number, radius = R) => {
        const phi = (90 - lat) * Math.PI / 180, theta = (lon + 180) * Math.PI / 180;
        return new T.Vector3(-radius * Math.sin(phi) * Math.cos(theta),
                             radius * Math.cos(phi),
                             radius * Math.sin(phi) * Math.sin(theta));
      };
      const store = window as unknown as {__geoTexture?: {key: string; canvas: HTMLCanvasElement}};
      const geoKey = `${input.id}:${(input.regions ?? []).map(r => r.label).join(",")}`;
      if (store.__geoTexture?.key !== geoKey) {
        const MAP_W = 4096, MAP_H = 2048;
        const c = document.createElement("canvas");
        c.width = MAP_W; c.height = MAP_H;
        const g = c.getContext("2d");
        if (g) {
          const trace = (ring: Ring) => {
            g.beginPath();
            ring.forEach(([lo, la], i) => {
              const x = (lo + 180) / 360 * MAP_W, y = (90 - la) / 180 * MAP_H;
              if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
            });
            g.closePath();
          };
          g.fillStyle = input.palette.bg || "#0b1220";
          g.fillRect(0, 0, MAP_W, MAP_H);
          // Land sits a clear step above the ocean so the coastline reads as a
          // shape on a phone, not as a wire drawing.
          g.fillStyle = input.palette.bg_soft || "#1b2740";
          for (const ring of input.world ?? []) { trace(ring); g.fill(); }
          g.strokeStyle = input.palette.grid || "#3a4a6b";
          g.lineWidth = 4; g.lineJoin = "round";
          for (const ring of input.world ?? []) { trace(ring); g.stroke(); }
          for (const region of input.regions ?? []) {
            const tone = region.tone === "primary" ? primary : secondary;
            g.fillStyle = tone;
            for (const ring of region.rings) { trace(ring); g.fill(); }
            g.strokeStyle = ink; g.lineWidth = 10;
            for (const ring of region.rings) { trace(ring); g.stroke(); }
          }
        }
        store.__geoTexture = {key: geoKey, canvas: c};
      }
      const mapTexture = new T.CanvasTexture(store.__geoTexture.canvas);
      mapTexture.colorSpace = T.SRGBColorSpace;
      mapTexture.anisotropy = 4;
      // Unlit: the palette is the brand's, and a light rig would darken half the
      // globe and destroy the contrast the canvas was drawn to guarantee.
      const globe = new T.Mesh(new T.SphereGeometry(R, 96, 96),
                               new T.MeshBasicMaterial({map: mapTexture}));
      scene.add(globe);
      const halo = new T.Mesh(new T.SphereGeometry(R * 1.035, 48, 48),
        new T.MeshBasicMaterial({color: secondary, transparent: true, opacity: .12,
                                 side: T.BackSide}));
      scene.add(halo);

      const legs = input.flight && input.flight.length
        ? input.flight
        : [{lon: -40, lat: 30, altitude: 3.4, hold: 1}];
      const weights = legs.map(w => Math.max(.05, w.hold));
      const total = weights.reduce((a, b) => a + b, 0);
      let travelled = progress * total, index = 0;
      while (index < legs.length - 1 && travelled > weights[index]) {
        travelled -= weights[index]; index += 1;
      }
      const from = legs[Math.max(0, index - 1)] ?? legs[0];
      const to = legs[index];
      const legT = Math.min(1, travelled / weights[index]);
      const smooth = legT * legT * (3 - 2 * legT);
      let dLon = to.lon - from.lon;
      if (dLon > 180) dLon -= 360; if (dLon < -180) dLon += 360;
      const lon = from.lon + dLon * smooth;
      const lat = from.lat + (to.lat - from.lat) * smooth;
      // FLOOR ON ALTITUDE. The first version descended to 0.30 while the pin head
      // sat at 0.32, so the camera ended up INSIDE the marker and the frame went
      // solid yellow. Nothing may bring the camera closer than this.
      const altitude = Math.max(1.15, from.altitude + (to.altitude - from.altitude) * smooth);
      camera.position.copy(toVec(lon, lat, R + altitude));
      camera.up.set(0, 1, 0);
      camera.lookAt(0, 0, 0);
      camera.near = .05; camera.far = 100; camera.updateProjectionMatrix();
      // Mobile framing: captions own the lower third, so the globe is pushed up
      // into the readable band instead of sitting dead centre behind them.
      scene.position.y = visibleH * 0.10;

      const geo = input.route;
      if (geo) {
        // A great-circle arc, lifted off the surface so it reads as a route
        // rather than a border. Tube geometry, because a line would be a hairline.
        const a = toVec(geo.from[0], geo.from[1], R).normalize();
        const b = toVec(geo.to[0], geo.to[1], R).normalize();
        const arcAt = (t: number) => {
          const v = new T.Vector3().copy(a).lerp(b, t).normalize();
          return v.multiplyScalar(R * (1 + .16 * Math.sin(Math.PI * t)));
        };
        // The route DRAWS ITSELF across the flight, so the money is visibly
        // moving rather than a static line waiting to be noticed.
        const drawn = Math.max(.02, Math.min(1, (progress - .28) / .46));
        const points = Array.from({length: 64}, (_, i) => arcAt(drawn * i / 63));
        const curve = new T.CatmullRomCurve3(points);
        scene.add(new T.Mesh(new T.TubeGeometry(curve, 64, R * .012, 8, false),
          new T.MeshBasicMaterial({color: primary})));
        const head = arcAt(drawn);
        const marker = new T.Mesh(new T.SphereGeometry(R * .028, 20, 20),
                                  new T.MeshBasicMaterial({color: ink}));
        marker.position.copy(head); scene.add(marker);
        const glow = new T.Mesh(new T.SphereGeometry(R * .055, 20, 20),
          new T.MeshBasicMaterial({color: primary, transparent: true, opacity: .45}));
        glow.position.copy(head); scene.add(glow);
        // The currency the marker is carrying, switching at the halfway point.
        text(drawn < .5 ? geo.fromLabel : geo.toLabel, -4.15, 128, primary);
      }

      // Region labels ride at their own coordinates and fade in as the camera
      // arrives, so USD and EUR are legible without covering the landmass.
      for (const region of input.regions ?? []) {
        const anchor = toVec(region.lon, region.lat, R * 1.02);
        const facing = anchor.clone().normalize().dot(
          camera.position.clone().normalize());
        if (facing < .12) continue;                 // on the far side of the globe
        const c = document.createElement("canvas");
        c.width = 1024; c.height = 256;
        const ctx = c.getContext("2d");
        if (!ctx) continue;
        ctx.fillStyle = region.tone === "primary" ? primary : secondary;
        ctx.font = `900 150px ${input.fontFamily}, Arial, sans-serif`;
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.lineWidth = 14; ctx.strokeStyle = input.palette.bg || "#0b1220";
        ctx.strokeText(region.label, 512, 128);
        ctx.fillText(region.label, 512, 128);
        const texture = new T.CanvasTexture(c);
        texture.colorSpace = T.SRGBColorSpace;
        const sprite = new T.Sprite(new T.SpriteMaterial({map: texture,
          transparent: true, opacity: Math.min(1, (facing - .12) * 4), depthTest: false}));
        sprite.scale.set(1.9, .48, 1);
        sprite.position.copy(anchor.multiplyScalar(1.06));
        scene.add(sprite);
      }
    } else if (input.template === "compound_growth") {
      const rate = Math.max(.01, (input.values[1] || 10) / 100);
      const points: Array<[number, number, number]> = [];
      const count = Math.max(2, Math.floor(60 * ease));
      for (let i = 0; i < count; i++) {
        const x = -4 + i / 59 * 8; const normalized = (Math.pow(1 + rate, i / 5) - 1) / (Math.pow(1 + rate, 11.8) - 1);
        points.push([x, -2.7 + normalized * 5.4, 0]);
      }
      line(points, positive); line([[-4, -2.7, 0], [4, -2.7, 0]], input.palette.grid || "#22304d");
      text(`${input.values[1] || 10}% COMPOUND GROWTH`, -3.35, 64, ink);
    }
    renderer.render(scene, camera);
    renderer.dispose();
  }, req, frame);
}

async function handleInternal(req: Request) {
  const started = performance.now();
  await mkdir(req.outputDir, {recursive: true});
  const p = await ensurePage(req);
  for (let frame = 0; frame < req.frames; frame++) {
    await renderFrame(p, req, frame);
    await p.screenshot({path: `${req.outputDir}/frame_${String(frame).padStart(5, "0")}.png`});
  }
  return {id: req.id, ok: true, renderMs: performance.now() - started,
          rssMb: aggregateRssMb()};
}

let renderQueue: Promise<unknown> = Promise.resolve();
export function handle(req: Request) {
  const current = renderQueue.then(() => handleInternal(req));
  renderQueue = current.catch(() => undefined);
  return current;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const input = createInterface({input: process.stdin, crlfDelay: Infinity});
  input.on("line", async line => {
    try { process.stdout.write(JSON.stringify(await handle(JSON.parse(line))) + "\n"); }
    catch (error) { process.stdout.write(JSON.stringify({ok: false, error: String(error)}) + "\n"); }
  });
  process.on("SIGTERM", async () => { if (browser) await browser.close(); process.exit(0); });
}
