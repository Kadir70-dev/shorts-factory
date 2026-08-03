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
  "dividend_cashflow" | "timeline_flythrough" | "compound_growth";
type Request = {
  id: string; outputDir: string; template: Template; width: number; height: number;
  fps: 30 | 60; frames: number; seed: number; title: string; label: string;
  values: number[]; labels: string[]; palette: Record<string, string>; fontFamily: string;
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

async function renderFrame(p: Page, req: Request, frame: number): Promise<void> {
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
    const text = (value: string, y: number, size: number, color: string, x = 0) => {
      const c = document.createElement("canvas"); c.width = 1536; c.height = 320;
      const ctx = c.getContext("2d")!; ctx.clearRect(0, 0, c.width, c.height);
      ctx.fillStyle = color; ctx.font = `900 ${size}px ${input.fontFamily}, Arial, sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(value, 768, 160, 1450);
      const texture = new T.CanvasTexture(c); texture.colorSpace = T.SRGBColorSpace;
      const sprite = new T.Sprite(new T.SpriteMaterial({map: texture, transparent: true}));
      sprite.scale.set(9.2, 1.92, 1); sprite.position.set(x, y, 1.8); scene.add(sprite);
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
      const max = Math.max(...input.values, 1);
      input.values.slice(0, 2).forEach((v: number, i: number) => {
        const h = 5.3 * v / max * ease; box(i ? 1.9 : -1.9, -2.5 + h / 2, 2.15, h, i ? secondary : primary);
        text(`${input.labels[i] || "VALUE"} ${v}`, -3.25, 60, ink, i ? 1.9 : -1.9);
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
