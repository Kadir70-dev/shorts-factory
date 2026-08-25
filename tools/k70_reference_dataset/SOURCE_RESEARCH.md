# K70 Premium Block-World Reference Dataset — Source Research

**Decision date:** 2026-08-25  
**Scope:** A private, local visual-reference library used for composition,
camera/framing, lighting, scene-density retrieval, and ranking. It is not a
source-art library and is not used to train a generative model.

## Executive decision

Use **Openverse and Wikimedia Commons as Tier A discovery surfaces**, always
preserving the original source page and verifying item-level rights. Use the
official **Flickr API only conditionally** and only after obtaining an API key
and resolving its short-cache requirement against the intended persistent
local library. Use **Modrinth only for metadata discovery** unless a gallery
image has its own explicit reusable license. Do not automate Planet Minecraft,
general forums, ArtStation, Sketchfab, or ad-hoc shader galleries.

This decision deliberately prioritizes provenance and authorized access over
raw visual volume. A public page, a downloadable URL, or a project-level
software license does not by itself license a gallery image.

## Ranked source audit

Volume figures below are discovery estimates, not promises. A bounded pilot is
required to measure *useful* volume after query, license, resolution, HUD/text,
quality, and duplicate filtering.

| Tier | Source | Useful volume estimate | Resolution / cinematic quality | Metadata and provenance | Access / rate limits | Duplicate risk | K70 decision |
|---|---|---:|---|---|---|---|---|
| **A** | Openverse | Hundreds to low thousands before filtering; useful yield unknown until pilot | Mixed; many irrelevant photos/graphics, but strong long-tail discovery across providers | Strong normalized creator, source, license, URLs; original-source verification remains mandatory | Public REST API; unauthenticated results are constrained and clients must honor response rate-limit headers | High across indexed providers | Primary discovery aggregator. Query broadly, canonicalize by original URL/hash, and download only through an eligible original source path. |
| **A** | Wikimedia Commons | Likely tens to low hundreds of Minecraft/voxel-relevant files; broad architecture references are much larger | Often high resolution; direct Minecraft cinematic yield likely low | Excellent per-file descriptions, authorship, license templates, and original URLs | Official Action API. Current guidance: meaningful User-Agent, no more than 3 concurrent requests, obey `Retry-After`; 200 req/min for compliant unauthenticated User-Agent at time of audit | Medium; derivatives and Flickr imports occur | Highest-confidence direct source. Preserve attribution and ShareAlike obligations per file. |
| **B** | Flickr API | Potentially thousands of query matches; premium pass rate unknown | Wide range from small screenshots to 4K shader captures | Good API fields and license filtering; all-rights-reserved is the upload default | API key required; documented ceiling 3,600 queries/hour. API terms say image caching is for reasonable periods and developer guide describes up to 24 hours, creating a material conflict with a permanent local corpus | High: reposts, albums, near-identical sequences | Discovery/pilot only until persistent-storage rights are resolved. Never scrape Flickr HTML. Only explicit licenses, owner restrictions, and source links. |
| **B** | Modrinth API | Hundreds to low thousands of relevant project gallery images | Often polished shader/mod promotional images; mixed UI/text | Project metadata is good; gallery-image rights are not reliably equivalent to project code/content license | Public reads usually require no token; 300 requests/minute per IP; unique User-Agent required | High within versions/projects | Metadata discovery only by default. Download only when the individual gallery image has explicit reusable rights and the API/source terms allow retention. |
| **C** | GitHub repositories/releases | Tens to hundreds from carefully selected voxel/open-source projects | Mixed documentation screenshots; occasional premium renders | Repository provenance is excellent, but a code license may not cover screenshots or third-party game assets | Official API/raw URLs; normal GitHub API limits apply | Medium | Per-repository opt-in only after confirming the license covers the specific image and no Minecraft-derived asset restriction defeats it. |
| **C** | Planet Minecraft | Visually, likely thousands | Often the strongest community builds/renders, but mixed thumbnails, text, and gameplay UI | Creator/page metadata exists; standardized reusable image licensing and bulk API are absent | No public bulk image API found. Planet has historically stated it does not want HTML scraped to form content | Very high: project galleries and reposted renders | Valuable human discovery signal, **not an automated collection source**. Do not scrape or bulk-download. |
| **C** | Community galleries/forums and shader showcases | Large but unbounded | Can be excellent; also heavy gameplay/UI/noise | Usually incomplete license metadata and unstable embeds | Site-specific; many lack suitable APIs and have anti-bot controls | Very high | Search only to identify creators/sources with explicit downloadable licenses. Never crawl generically. |
| **REJECT** | ArtStation | Large visual pool | Excellent art quality | Creator ownership; licensing for local dataset reuse usually absent | Terms prohibit unpermitted collection/scraping and restrict NoAI content use | High | No automated collection. |
| **REJECT** | Sketchfab screenshots/previews | Moderate voxel pool, wrong medium | 3D preview captures, watermarks/UI | Model licenses exist, but preview-image reuse is not equivalent; authenticated download API is for models | Terms restrict collection/aggregation and prohibit hiding viewer watermark | Medium | Exclude as an image source. |
| **REJECT** | CurseForge galleries | Large mod ecosystem | Promotional quality varies | API project metadata; screenshot rights remain uploader-specific | API key and platform-purpose restrictions; API search capped at 10,000 results | High | Not justified for this reference-image purpose. |
| **REJECT** | Generic search engines, Pinterest, repost sites | Very large | Uncontrolled | Weak or missing original provenance and rights | No authorized bulk collection path | Extreme | Never use as download sources. They may only lead to an original eligible page. |

## Primary-source findings

- [Openverse](https://make.wordpress.org/openverse/) describes itself as an
  openly accessible search engine/API for openly licensed media. It indexes,
  rather than hosts, third-party files; therefore K70 must verify and retain the
  original source and license. Its official client documentation says callers
  must implement rate-limit backoff themselves.
- [Flickr's API developer guide](https://www.flickr.com/services/developer/api/)
  states 3,600 queries/hour per key, says not to screen-scrape, and describes
  short-term caching of API results/images. [Flickr API terms](https://www.flickr.com/help/terms/api)
  make the uploader's restrictions controlling and say commercial uses require
  an appropriate Creative Commons license unless separately authorized.
- [Wikimedia's 2026 API limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)
  specify a meaningful User-Agent, at most three concurrent requests, and
  `Retry-After` handling; a compliant unauthenticated User-Agent currently gets
  200 requests/minute. [Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/licenses/en)
  explains that each file's license and attribution/ShareAlike terms govern.
- [Modrinth API documentation](https://docs.modrinth.com/api/) states most reads
  are unauthenticated, requires a uniquely identifying User-Agent, exposes rate
  headers, and currently limits clients to 300 requests/minute. Its
  [terms](https://modrinth.com/legal/terms) allow API access subject to third-party
  rights; they do not establish that every project gallery image is reusable
  under the project's declared license.
- Planet Minecraft has no verified public image API. A
  [Planet Minecraft staff/community explanation](https://www.planetminecraft.com/blog/what-happened-to-the-pmc-overlay-mod/)
  records the site's position against scraping HTML to form content. This is
  sufficient to withhold automation even though the site is visually useful.
- [Minecraft's Usage Guidelines](https://www.minecraft.net/en-us/usage-guidelines)
  define screenshots as Minecraft assets and impose context-specific rules.
  Separately, each community screenshot also has creator copyright. A Creative
  Commons label from the creator does not erase Mojang/Microsoft conditions.
- [ArtStation terms](https://www.artstation.com/tos) and
  [Sketchfab terms](https://sketchfab.com/terms) contain explicit collection,
  scraping, and/or NoAI restrictions. They are excluded rather than worked
  around.

## Existing engineering components

| Need | Existing option | Decision |
|---|---|---|
| Bounded HTTP download | `httpx` already installed | **Reuse.** K70 needs source-aware pacing, content-length caps, MIME sniffing, checkpoints, and provenance; a small orchestrator around `httpx` is safer than a high-throughput generic downloader. |
| Massive URL downloading | [`img2dataset`](https://github.com/rom1504/img2dataset), MIT | Do not adopt initially. It is excellent at huge generic sets and supports SHA-256, incremental shards, metadata, and opt-out headers, but K70's per-source license/access gates and modest 20k–50k scale favor controlled downloads. Revisit only after candidate URLs are fully approved. |
| Decode/resize/contact sheets | Pillow already installed | **Reuse.** |
| Exact hash | Python `hashlib` | **Reuse.** |
| Perceptual hash | `ImageHash` or [`imagededup`](https://github.com/idealo/imagededup), Apache-2.0 | Prefer the small `ImageHash` dependency for pHash/dHash; do not pull TensorFlow-heavy `imagededup` merely for hashing. Add embedding-neighbor confirmation for crops/reposts. |
| Semantic embeddings | Existing `transformers` + `torch` and repository `clip_rank.py` using `openai/clip-vit-base-patch32` | **Reuse the installed stack and factor a dataset-safe embedding adapter.** No additional large model initially. Benchmark CPU throughput and model-cache size before enabling. |
| Aesthetic score | [LAION aesthetic predictor](https://github.com/LAION-AI/aesthetic-predictor), MIT | Conditional auxiliary signal only. Its own description is a linear predictor over CLIP and cannot replace K70-specific cinematic prompts or visual inspection. |
| OCR/text rejection | PaddleOCR, Apache-2.0 | Technically strong and Windows-capable, but not installed and larger than needed for Gate 1. Start with a lightweight local detector only if available; add PaddleOCR after a Top-100 error analysis proves text leakage is material. |
| Vector search | NumPy exact cosine for 5,000 vectors; FAISS, MIT, is Windows-capable | **Use NumPy initially.** 5,000×512 float vectors are small; FAISS adds installation complexity without material benefit. Keep the index format migratable. |
| Quality metrics | Pillow/NumPy; optional OpenCV/pyiqa | Use deterministic decode, size, entropy, exposure, clipping, and edge-energy metrics. Do not present them as aesthetic understanding. CLIP multi-prompt relevance + a separately calibrated aesthetic signal handle semantics. |
| Metadata | SQLite standard library | **Reuse.** Transactions and stage tables provide checkpoints without another service. |

## Recommended scoring architecture

No single metric decides admission. Hard gates run first: authorized source,
eligible license policy, real image decode/MIME, size cap, minimum dimensions,
pathological alpha, exact hash, pHash/dHash cluster, and high OCR/UI/meme risk.
Survivors receive separately stored signals:

1. technical quality (resolution, blur/edge energy, exposure/clipping, entropy),
2. positive multi-prompt CLIP relevance,
3. negative multi-prompt CLIP relevance (HUD, menu, meme, tutorial, ordinary gameplay),
4. optional aesthetic predictor,
5. depth/lighting/density/shot-type prompt scores,
6. source/creator/gallery saturation penalty,
7. embedding novelty/diversity.

Thresholds are fixed before scaling. If a later gate yields fewer images, the
pipeline discovers more candidates; it does not lower thresholds. Scores and
inferred tags retain component values and confidence rather than pretending to
be ground truth.

## Phase-0 gap matrix

| Claim / decision | Evidence confidence | Remaining gap | Required next action |
|---|---|---|---|
| Wikimedia can be collected responsibly | High | Query-specific useful volume | Run a metadata-only discovery pilot, then download a small licensed sample. |
| Openverse is the best broad discovery surface | High for access/provenance; medium for yield | Anonymous pagination constraints and cinematic yield | Register API credentials if needed; run metadata-only query matrix. |
| Flickr can populate a persistent local corpus | Low/blocked | API caching language conflicts with permanent storage | Do not bulk download; seek clarification or use eligible originals surfaced through a different authorized channel. |
| Modrinth gallery licenses are reusable | Low | Item-level gallery rights often absent | Treat as metadata-only unless explicit image rights are found. |
| 5,000 premium eligible images exist | Unknown | No legitimate pilot counts yet | Top-100 gate must answer this; never extrapolate from search result counts. |
| CLIP ViT-B/32 is sufficient on this CPU-only Windows host | Medium | Actual throughput and K70 prompt separation | Benchmark on the first authorized sample before model expansion. |
| 106.3 GB free space is enough | Medium | Actual source image sizes | Enforce a 60 GB temporary cap and estimate again after Top 100 and 1,000. |

## Resource envelope before collection

- Free disk observed: **106.3 GiB**.
- Initial temporary hard cap: **60 GiB**; stop discovery/download before breach.
- Maximum file: **25 MiB**; reject from headers or streamed byte count.
- Network concurrency: global **4**, source default **1–2**, never above a
  source's published guidance.
- Timeout: connect 10 s, read 30 s; two retries with exponential backoff and
  jitter; obey `Retry-After` exactly.
- Preserve originals; thumbnails and embeddings are derived and rebuildable.
- No bulk-download flag is enabled until the Top-100 pipeline and audit pass.

## Research stopping rationale

The current evidence is sufficient to choose safe pilot sources and reject
high-risk ones. Additional broad gallery searching would not resolve the main
uncertainties, which are empirical yield and image quality. Those must be
answered by bounded, authorized metadata and Top-100 pilots rather than more
speculation.

## Live metadata pilot result

The bounded 2026-08-25 Openverse pilot ran 30 targeted queries over two
anonymous pages each (the documented anonymous maximum is 20 results/page).
It saw **69** results and inserted **66** new unique records with no request
errors. Source distribution was Flickr 47, Wikimedia 14, Geograph 5, and
Sketchfab 1. Metadata inspection found the results overwhelmingly irrelevant:
ordinary real-world architecture, repeated shots from one building/gallery,
and unrelated scientific/automotive material. Only two titles were plausibly
Minecraft-related, and both were Flickr items that remain metadata-only under
the persistent-storage review.

The direct Wikimedia pilot returned an explicit HTTP 403 asking the client to
respect Wikimedia's robot policy. Its 2026 policy requires an identifying
User-Agent with real contact information; none is configured in this local
project, so the pipeline did not invent an identity or retry around the block.

**Gate conclusion:** the Top-100 premium gate is **NO / not feasible from the
currently authorized pool**. No images were bulk-downloaded, and thresholds
were not lowered. Flickr requires an API key not present in the environment;
Planet Minecraft/general galleries lack an authorized bulk route; Modrinth
gallery-image rights are not reliably established by project metadata. These
are access/right constraints, not engineering defects.
