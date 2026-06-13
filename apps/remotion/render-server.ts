/**
 * Warm render service. Bundles ONCE at boot, then renders on POST /render.
 * Avoids paying the webpack bundle cost on every video. The FastAPI render
 * stage POSTs {composition, props_path, out, frames, fps} here.
 */
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import path from "node:path";

const PORT = 3001;
let serveUrl: string;

// NOTE: a bundle-once warm service can only serve assets that exist in the public
// dir AT BOOT — Remotion bakes the public dir into `serveUrl` at bundle time, so
// per-job assets written later (resolved footage, AI images/plates, the job's
// voiceover) 404 via staticFile(). Passing publicDir to renderMedia does NOT
// override a pre-built serveUrl. So real jobs render through the Remotion-CLI
// fallback in render.py (which re-bundles per job with remotion.config.ts's
// setPublicDir=data/ — correct, just not warm). Making THIS service serve live
// per-job assets needs a follow-up (serve data/ over HTTP + URL-based src, or
// re-bundle per render). Left as-is to avoid shipping an unverified fix.
async function boot() {
  serveUrl = await bundle({ entryPoint: path.join(__dirname, "src/index.ts") });
  console.log("[remotion] bundle ready");
}

const server = createServer(async (req, res) => {
  if (req.method !== "POST" || req.url !== "/render") {
    res.writeHead(404).end();
    return;
  }
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", async () => {
    try {
      const { props_path, out } = JSON.parse(body);
      const inputProps = JSON.parse(readFileSync(props_path, "utf8"));
      const composition = await selectComposition({
        serveUrl, id: "Short", inputProps,
      });
      await renderMedia({
        serveUrl, composition, codec: "h264",
        outputLocation: out, inputProps,
        concurrency: 2,
      });
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true, out }));
    } catch (e) {
      res.writeHead(500).end(JSON.stringify({ error: String(e) }));
    }
  });
});

boot().then(() => server.listen(PORT, () =>
  console.log(`[remotion] render server on :${PORT}`)));
