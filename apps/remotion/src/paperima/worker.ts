/**
 * Headless Puppeteer worker driving the locally-installed Paperima app
 * (github.com/nurimator/paperima, AGPL-3.0-only, commit afc361527b66).
 *
 * Paperima is a browser-only canvas app with NO CLI and NO scriptable API —
 * a human uploads an image, drags sliders, and clicks Export. This worker
 * automates exactly that surface with Puppeteer, the same way a person
 * would: it never imports, requires, or reads Paperima's own source as a
 * module, and never modifies Paperima's files. It only (a) serves Paperima's
 * own unmodified production build (`npm run build` output) from a plain
 * static file server spun up in this process, and (b) drives the resulting
 * page through Chromium exactly like `apps/remotion/src/threejs/worker.ts`
 * drives its Three.js page. That is the "external/local process" boundary
 * the integration is required to keep: Paperima runs unmodified, in its own
 * browser tab, and this file only pushes DOM events at it and reads back
 * whatever file it downloads. AGPL-3.0's network-copyleft clause targets
 * DISTRIBUTING A MODIFIED Paperima to remote users over a network — running
 * an unmodified upstream build as a subprocess-controlled local tool (the
 * same pattern already used here for Scribus, GPL-2.0) is not that.
 *
 * Why UI automation instead of calling internals directly: `startExport` IS
 * exposed on `window` after the export module lazy-loads, but it closes over
 * a module-private `state` object that Paperima never exposes — there is no
 * project-import/export or public config API. Driving the real inputs is
 * the only stable integration surface; it is also the one least likely to
 * break silently across a Paperima upgrade (internal refactors change
 * closures far more often than user-facing control ids).
 */
import {createInterface} from "node:readline";
import {createServer, type Server} from "node:http";
import {readFile, mkdir, writeFile} from "node:fs/promises";
import {existsSync} from "node:fs";
import {extname, join, resolve} from "node:path";
import puppeteer, {type Browser, type Page} from "puppeteer";

type AnimationType = "reveal" | "conceal" | "dynamic" | "wobble" | "static";
type BackgroundMode = "greenscreen" | "white" | "black";

type Request = {
  id: string;
  /** Path to Paperima's OWN unmodified `dist/` build (external install —
   *  never copied into this repo). Resolved by paperima_engine.py. */
  distDir: string;
  imagePath: string;
  outputPath: string;
  animationType: AnimationType;
  durationSec: number;
  fps: number;
  /** Used only to pick the closest built-in aspect-ratio preset — Paperima
   *  exposes 9:16 / 16:9 / 4:3 / 1:1 buttons, not arbitrary pixel dims. */
  width: number;
  height: number;
  shadowStrength: number;   // 0-100, maps to shadow opacity + blur
  textureIndex: number;     // 0-5, paper fold overlay texture variant
  wobbleStrength: number;   // 0-10, movement.simpelStrength
  backgroundMode: BackgroundMode;
  timeoutMs: number;
};

type Response =
  | {id: string; ok: true; outputPath: string; renderMs: number; downloadedBytes: number}
  | {id: string; ok: false; error: string};

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json",
  ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml",
  ".ico": "image/x-icon", ".ttf": "font/ttf", ".webmanifest": "application/manifest+json",
};

let browser: Browser | null = null;
let server: Server | null = null;
let servedDistDir = "";
let serverOrigin = "";

/** Serves Paperima's OWN build output verbatim — no transformation, no
 * injection into its files. Starts once per distDir, reused across jobs. */
async function ensureServer(distDir: string): Promise<string> {
  // `resolve` normalises separators (the caller may pass forward slashes on
  // Windows, e.g. from a JSON job payload) so the startsWith() containment
  // check below compares like with like — a raw string mismatch here 403'd
  // even the correct index.html path during initial testing.
  const root = resolve(distDir);
  if (server && servedDistDir === root) return serverOrigin;
  if (server) { server.close(); server = null; }
  server = createServer(async (req, res) => {
    try {
      let p = decodeURIComponent((req.url || "/").split("?")[0]);
      if (p === "/") p = "/index.html";
      const full = resolve(join(root, p));
      if (!full.startsWith(root)) { res.writeHead(403); res.end(); return; }
      const body = await readFile(full);
      res.writeHead(200, {"content-type": MIME[extname(full)] || "application/octet-stream"});
      res.end(body);
    } catch {
      res.writeHead(404); res.end();
    }
  });
  await new Promise<void>((resolve, reject) => {
    server!.once("error", reject);
    server!.listen(0, "127.0.0.1", () => resolve());
  });
  const addr = server.address();
  if (!addr || typeof addr === "string") throw new Error("static server failed to bind");
  servedDistDir = root;
  serverOrigin = `http://127.0.0.1:${addr.port}`;
  return serverOrigin;
}

async function ensureBrowser(): Promise<Browser> {
  if (browser && browser.connected) return browser;
  browser = await puppeteer.launch({
    headless: true,
    executablePath: process.env.PAPERIMA_BROWSER_EXECUTABLE || undefined,
    args: [
      "--disable-dev-shm-usage", "--no-sandbox", "--autoplay-policy=no-user-gesture-required",
      // Paperima's render/export loop runs on requestAnimationFrame. Chrome
      // throttles (and can all but pause) rAF in tabs it considers
      // backgrounded/occluded — true of every headless Puppeteer page, which
      // is never actually visible. Without these three flags the export
      // modal appears (the click and the FIRST frame both work) and then
      // hangs indefinitely: confirmed empirically — encoding never completed
      // even at a 150s timeout for a 4s clip that exports in ~8s headed.
      "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
      "--disable-background-timer-throttling",
    ],
  });
  return browser;
}

/** Sets a native input/select value and fires the events Paperima's own
 * listeners expect — bypasses framework/property shadowing on `.value =`. */
async function setValue(page: Page, id: string, value: string | number | boolean): Promise<void> {
  await page.evaluate((elId, val) => {
    const el = document.getElementById(elId) as HTMLInputElement | HTMLSelectElement | null;
    if (!el) throw new Error(`Paperima control not found: #${elId}`);
    if (typeof val === "boolean" && el instanceof HTMLInputElement && el.type === "checkbox") {
      if (el.checked !== val) el.click();          // real click, not just a flag flip
      return;
    }
    const proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
    setter.call(el, String(val));
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  }, id, value as any);
}

async function clickById(page: Page, id: string): Promise<void> {
  await page.evaluate(elId => {
    const el = document.getElementById(elId);
    if (!el) throw new Error(`Paperima control not found: #${elId}`);
    (el as HTMLElement).click();
  }, id);
}

const ASPECT_PRESETS: Array<[string, number]> = [["9/16", 9 / 16], ["4/3", 4 / 3],
  ["1/1", 1], ["16/9", 16 / 9]];

function closestAspect(width: number, height: number): string {
  const target = width / height;
  return ASPECT_PRESETS.reduce((best, cur) =>
    Math.abs(cur[1] - target) < Math.abs(best[1] - target) ? cur : best)[0];
}

async function configureObject(page: Page, req: Request): Promise<void> {
  // Object tab: torn edges stay on (Paperima's default) — that IS the paper
  // silhouette; shadow strength maps to both opacity and blur so "stronger"
  // reads as both darker and softer, matching how a real cast shadow scales.
  await clickById(page, "handle-object");
  const shadowOpacity = Math.max(0, Math.min(100, req.shadowStrength));
  const shadowBlur = Math.round(4 + (shadowOpacity / 100) * 20);
  await setValue(page, "shadow-enabled-switch", true);
  await setValue(page, "shadow-opacity-input", shadowOpacity);
  await setValue(page, "shadow-blur-input", shadowBlur);

  await setValue(page, "paper-fold-overlay-enabled-switch", true);

  const wobble = Math.max(0, Math.min(10, req.wobbleStrength));
  if (req.animationType === "wobble") {
    await setValue(page, "movement-enabled-switch", true);
    await setValue(page, "movement-simpel-strength-input", wobble || 1.5);
    await setValue(page, "movement-simpel-speed-input", 1);
  } else if (req.animationType === "static") {
    await setValue(page, "movement-enabled-switch", false);
  } else {
    // reveal/conceal/dynamic: a LIGHT idle wobble under the primary motion
    // so the paper never looks perfectly rigid, without fighting it.
    await setValue(page, "movement-enabled-switch", true);
    await setValue(page, "movement-simpel-strength-input", Math.min(wobble, 1));
  }
}

async function configureBackground(page: Page, req: Request): Promise<void> {
  await clickById(page, "handle-background");
  const color = req.backgroundMode === "white" ? "#ffffff"
    : req.backgroundMode === "black" ? "#000000" : "#00ff00";
  await setValue(page, "background-color", color);
}

async function configureAnimation(page: Page, req: Request): Promise<void> {
  await clickById(page, "handle-animasi");
  if (req.animationType === "dynamic") {
    // "Advanced" mode's own shipped default keyframes (scale 50 -> 80 over
    // the timeline) are a real, distinct zoom/reveal motion — used as-is
    // rather than hand-authoring new keyframes through the timeline UI,
    // which has no stable per-keyframe ids to script against reliably.
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll("button"))
        .find(b => (b.textContent || "").trim() === "Advanced");
      if (!btn) throw new Error("Paperima Advanced control-mode button not found");
      (btn as HTMLElement).click();
    });
    return;
  }
  await setValue(page, "simple-anim-open-switch", req.animationType === "reveal");
  await setValue(page, "simple-anim-close-switch", req.animationType === "conceal");
}

async function configureExportSettings(page: Page, req: Request): Promise<void> {
  const ratio = closestAspect(req.width, req.height);
  await page.evaluate(target => {
    const btn = Array.from(document.querySelectorAll<HTMLButtonElement>("button[data-ratio]"))
      .find(b => b.dataset.ratio === target);
    if (btn) btn.click();
  }, ratio);
}

/** Polls a boolean-returning page predicate every `stepMs` until it flips or
 * `timeoutMs` elapses. Used for both "the export modal appeared" (proves the
 * click landed) and "the captured Blob is ready" (proves encoding finished)
 * — plain polling rather than a page-side Promise because a page-side wait
 * that outlives Puppeteer's own timeout has nothing to cancel it. */
async function waitForPageCondition(page: Page, predicate: () => boolean,
                                    timeoutMs: number, stepMs = 300): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.evaluate(predicate)) return true;
    await new Promise(r => setTimeout(r, stepMs));
  }
  return false;
}

async function runExport(page: Page, req: Request, outputPath: string): Promise<number> {
  await clickById(page, "export-video-btn-header");
  console.error("[paperima] clicked export button, waiting for the settings dialog...");
  // The header button opens a CONFIRMATION dialog (format/resolution/fps/
  // duration/filename, "Cancel" / "Start Export") — it does not export
  // directly. This step was missed on the first pass here (found only by
  // screenshotting the page mid-"hang": the dialog was sitting open the
  // whole time, unclicked, which is why encoding never appeared to start).
  const settingsSeen = await waitForPageCondition(page, () =>
    !!document.getElementById("start-export-with-settings-btn")
      && (document.getElementById("start-export-with-settings-btn") as HTMLElement).offsetParent !== null,
    Math.min(10_000, req.timeoutMs));
  if (settingsSeen) {
    await clickById(page, "start-export-with-settings-btn");
    console.error("[paperima] confirmed export settings dialog");
  }
  console.error("[paperima] waiting for the export-progress modal...");
  // Confirming the settings dialog can retrigger Paperima's own torn-edge
  // cache regeneration first (observed: "Starting progressive cache
  // generation..." logged again right after the click) — give that room to
  // finish before deciding the export never started.
  const modalSeen = await waitForPageCondition(page, () =>
    Array.from(document.querySelectorAll("*")).some(el => (el.textContent || "").includes("Exporting Video")),
    Math.min(30_000, req.timeoutMs));
  if (!modalSeen) {
    throw new Error("Paperima did not start exporting — the Export button click had no visible effect");
  }
  console.error("[paperima] export in progress, waiting for the encoded Blob...");
  // Opt-in mid-export screenshot, purely a debugging aid (set
  // PAPERIMA_DEBUG_SHOT=<path.png>) — this is how the settings-confirmation
  // dialog and the background-tab rAF-throttling issue above were actually
  // diagnosed; left in place since headless UI automation against a
  // third-party app someone else maintains WILL need this again someday.
  if (process.env.PAPERIMA_DEBUG_SHOT) {
    setTimeout(() => {
      page.screenshot({path: process.env.PAPERIMA_DEBUG_SHOT as `${string}.png`})
        .then(() => console.error("[paperima] debug screenshot saved"))
        .catch(e => console.error("[paperima] debug screenshot failed", String(e)));
    }, 8000);
  }
  const blobReady = await waitForPageCondition(page,
    () => (window as any).__paperimaBlob instanceof Blob, req.timeoutMs);
  if (!blobReady) {
    throw new Error(`Paperima did not finish encoding within ${req.timeoutMs}ms`);
  }
  console.error("[paperima] blob ready, reading bytes back...");
  // Transferred as base64 through evaluate()'s JSON channel — Puppeteer has
  // no first-class "give me this in-page Blob as a Node Buffer" primitive.
  // Fine at these sizes (single-digit MB for a few seconds of 1080x1920).
  const base64 = await page.evaluate(async () => {
    const blob: Blob = (window as any).__paperimaBlob;
    const buf = await blob.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  });
  const bytes = Buffer.from(base64, "base64");
  if (bytes.length === 0) throw new Error("Paperima export produced an empty file");
  await mkdir(join(outputPath, ".."), {recursive: true});
  await writeFile(outputPath, bytes);
  return bytes.length;
}

async function handleInternal(req: Request): Promise<Response> {
  const started = performance.now();
  try {
    if (!existsSync(req.distDir)) {
      throw new Error(`Paperima build not found at ${req.distDir} — run \`npm run build\` `
        + "in the Paperima checkout first.");
    }
    if (!existsSync(req.imagePath)) {
      throw new Error(`source image not found: ${req.imagePath}`);
    }
    console.error("[paperima] starting server...");
    const origin = await ensureServer(req.distDir);
    console.error("[paperima] server up at", origin);
    const b = await ensureBrowser();
    console.error("[paperima] browser ready");
    const page = await b.newPage();
    try {
      await page.setViewport({width: 1024, height: 768});
      page.on("console", m => console.error("[page console]", m.type(), m.text()));
      page.on("pageerror", e => console.error("[page error]", String(e)));
      page.on("requestfailed", r => console.error("[page reqfail]", r.url(), r.failure()?.errorText));
      // Paperima's own export path (src/modules/export-module.js) wraps the
      // finished video in a Blob, calls URL.createObjectURL on it, and
      // clicks a synthetic <a download> to hand it to the browser — headless
      // Chrome's CDP download interception does not reliably fire for a
      // blob: URL triggered this way (confirmed empirically: no
      // Page.downloadWillBegin event, no file, no error — the export
      // completes inside the page and the bytes just go nowhere). Observing
      // which Blob gets passed to URL.createObjectURL and reading it back
      // via blob.arrayBuffer() sidesteps the browser download pipeline
      // entirely. This only WATCHES a standard Web API call Paperima's
      // unmodified code already makes — it does not alter Paperima's
      // behaviour or output in any way.
      await page.evaluateOnNewDocument(() => {
        (window as any).__paperimaBlob = null;
        const original = URL.createObjectURL.bind(URL);
        URL.createObjectURL = (obj: Blob | MediaSource) => {
          if (obj instanceof Blob && obj.size > 0) (window as any).__paperimaBlob = obj;
          return original(obj as Blob);
        };
      });
      console.error("[paperima] navigating...");
      await page.goto(origin, {waitUntil: "load", timeout: req.timeoutMs});
      console.error("[paperima] page loaded, waiting for #image-upload...");
      await page.waitForSelector("#image-upload", {timeout: req.timeoutMs});
      console.error("[paperima] found #image-upload, uploading file...");

      const fileInput = await page.$("#image-upload");
      if (!fileInput) throw new Error("Paperima object-image file input not found");
      await (fileInput as unknown as {uploadFile(p: string): Promise<void>}).uploadFile(req.imagePath);
      console.error("[paperima] file uploaded, waiting for it to register...");
      // Paperima decodes + draws the uploaded image asynchronously with no
      // exposed "ready" event; the thumbnail swapping from the drop-zone
      // icon to a filename chip is the real signal a human waits for too.
      await page.waitForFunction(() => {
        const el = document.getElementById("image-upload");
        return !!el && !!(el as HTMLInputElement).files?.length;
      }, {timeout: req.timeoutMs});
      await new Promise(r => setTimeout(r, 400));

      console.error("[paperima] configuring object...");
      await configureObject(page, req);
      console.error("[paperima] configuring background...");
      await configureBackground(page, req);
      console.error("[paperima] configuring animation...");
      await configureAnimation(page, req);
      await setValue(page, "export-duration-input", req.durationSec);
      const fpsSelect = await page.$("#export-fps-select");
      if (fpsSelect) await setValue(page, "export-fps-select", String(req.fps));
      const formatSelect = await page.$("#export-format-select");
      if (formatSelect) await setValue(page, "export-format-select", "mp4");
      await configureExportSettings(page, req);
      console.error("[paperima] config done, starting export...");

      const sizeBytes = await runExport(page, req, req.outputPath);
      console.error("[paperima] export finished:", req.outputPath, sizeBytes, "bytes");

      return {id: req.id, ok: true, outputPath: req.outputPath,
              renderMs: performance.now() - started, downloadedBytes: sizeBytes};
    } finally {
      await page.close().catch(() => undefined);
    }
  } catch (error) {
    return {id: req.id, ok: false, error: String((error as Error)?.message || error)};
  }
}

let queue: Promise<unknown> = Promise.resolve();
export function handle(req: Request): Promise<Response> {
  const current = queue.then(() => handleInternal(req));
  queue = current.catch(() => undefined);
  return current as Promise<Response>;
}

if (process.argv[1] && process.argv[1].endsWith("worker.js")) {
  const input = createInterface({input: process.stdin, crlfDelay: Infinity});
  input.on("line", async line => {
    if (!line.trim()) return;
    try { process.stdout.write(JSON.stringify(await handle(JSON.parse(line))) + "\n"); }
    catch (error) { process.stdout.write(JSON.stringify({ok: false, error: String(error)}) + "\n"); }
  });
  process.on("SIGTERM", async () => {
    if (server) server.close();
    if (browser) await browser.close();
    process.exit(0);
  });
}
