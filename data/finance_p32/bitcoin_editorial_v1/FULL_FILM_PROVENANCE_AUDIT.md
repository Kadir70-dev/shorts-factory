# FULL-FILM PROVENANCE AUDIT: The World Before Bitcoin (Ep. 1)

- **Graph:** `scene_graph_p32.json` (156 scenes, 656.942 s, timeline frozen).
- **Audit date:** 2026-10-22.
- **Method:** live Wikimedia Commons metadata; stock URLs recovered offline by matching sha1(URL) from the P3 provider search cache against cache filenames (21/21); frame review of every stock or kept still; code and report inspection for generated layers.
- **This is a technical provenance audit, not legal advice.**

## Summary by layer

| Layer | Scenes | Source | Commercial YouTube | Attribution |
|---|---|---|---|---|
| Archival stills (Commons) | 26 | Wikimedia Commons: PD / CC0 / CC BY only (no ShareAlike left) | allowed | required for 5 CC BY files: s28, s80, s82, s108, s132 |
| K70 original graphics / typography | 9 | Pillow plates (`editorial_plates`, `explainer_graphics`) | allowed | no |
| Stock video | 21 | Pexels (all 21 recovered) | allowed under the Pexels License (no sale of unaltered copies; no endorsement or offensive use of identifiable people) | not required |
| Kinetic cards | 50 | local render, OFL fonts | allowed | no |
| Charts | 22 | local render; data sources in overlays | allowed | cite data sources (already on screen) |
| Three.js | 20 | K70 `globe_flight`, three.js (MIT), Natural Earth + US Census borders (PD) | allowed | no |
| AI cinematic | 8 | Pollinations `flux` stills + local motion | **verify**: Pollinations publishes no output-licence terms we could retrieve; third-party sources say `flux` = FLUX.1 schnell (Apache-2.0) | no; **AI disclosure required** |
| Voice | 156 | Kokoro v1.0 ONNX (`kokoro-v1.0.onnx`, Apache-2.0), voice `am_michael` | allowed | no; synthetic voice, so tick YouTube's disclosure if it applies |
| Music | 1 bed | `documentary_a.wav`, synthesized by `pipeline/music.py` with ffmpeg sine sources (generated 2026-10-20) | allowed (original) | no |
| SFX | 16 cues | 8-piece pack synthesized by `pipeline/sfx.py` with ffmpeg | allowed (original) | no |
| Fonts | — | Archivo Black, Barlow Condensed, IBM Plex Mono, Anton (SIL OFL 1.1, verified in font name tables); Noto / DejaVu for P3.2 plates | allowed | no |

## YouTube compliance notes

- `meta.requires_ai_disclosure` is **true** (24 scenes are listed in `ai_disclosure_reasons`). When uploading, set "Altered or synthetic content" to **Yes**.
- Paste the credits block from `FINAL_VIDEO_CREDITS.md` into the description.
- Pexels and Commons content carries no Content ID claims known to us. The music is synthesized, so no claim risk is expected.
- The "Not financial advice" disclaimer is already in the description metadata.

## Per-scene table

| Scene | Start | Type | Source | Licence | Attribution | Notes |
|---|---|---|---|---|---|---|
| s1 | 0:00.0 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s2 | 0:06.2 | dataviz | K70 chart (local render); data: Federal Reserve History | Original; fonts SIL OFL 1.1 | no |  |
| s3 | 0:11.2 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s4 | 0:15.6 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s5 | 0:17.4 | image | Commons [United States Bullion Depository 1939.tiff](https://commons.wikimedia.org/wiki/File:United_States_Bullion_Depository_1939.tiff) | Public domain | no | U.S. Bullion Depository, Fort Knox · 1939 |
| s6 | 0:19.0 | image | Commons ["Marine One" in flight - NARA - 194719.tif](https://commons.wikimedia.org/wiki/File:%22Marine_One%22_in_flight_-_NARA_-_194719.tif) | Public domain | no | Marine One in flight · March 1971 |
| s7 | 0:25.1 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s8 | 0:29.1 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s9 | 0:33.2 | image | Commons [Exterior of Camp David lodge with swimming pool in fore](https://commons.wikimedia.org/wiki/File:Exterior_of_Camp_David_lodge_with_swimming_pool_in_foreground._-_NARA_-_194350.tif) | Public domain | no | Camp David · February 1971 |
| s10 | 0:38.9 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s11 | 0:44.2 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s12 | 0:47.4 | broll | Pexels video [8369976](https://www.pexels.com/video/8369976/) | Pexels License | no (optional) | OK: illustrative (piggy bank) |
| s13 | 0:55.0 | broll | Pexels video [7612013](https://www.pexels.com/video/7612013/) | Pexels License | no (optional) | WEAK: modern pen-and-paper close-up for 1944; generic, not false |
| s14 | 0:58.3 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s15 | 1:07.3 | image | Commons [5 Millionen Mark 1923-08-20.jpg](https://commons.wikimedia.org/wiki/File:5_Millionen_Mark_1923-08-20.jpg) | Public domain | no | 5 million marks · 20 August 1923 |
| s16 | 1:09.8 | image | Commons [1923 Germany rampant Inflation Medal, Mittweida, Saxony](https://commons.wikimedia.org/wiki/File:1923_Germany_rampant_Inflation_Medal,_Mittweida,_Saxony,_reverse.jpg) | Public domain | no | 1923 inflation medal: 1 lb of bread = 80 billion marks |
| s17 | 1:14.5 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s18 | 1:19.2 | broll | Pexels video [30794067](https://www.pexels.com/video/30794067/) | Pexels License | no (optional) | OK: metaphor (chain-link) |
| s19 | 1:20.8 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s20 | 1:24.7 | dataviz | K70 chart (local render); data: Bretton Woods Agreement, 1944 | Original; fonts SIL OFL 1.1 | no |  |
| s21 | 1:30.3 | broll | Pexels video [4694342](https://www.pexels.com/video/4694342/) | Pexels License | no (optional) | WEAK: unrelated modern woman; not historically false, low relevance |
| s22 | 1:34.4 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s23 | 1:39.5 | image | Commons [Main Street, looking north, Greenville.jpg](https://commons.wikimedia.org/wiki/File:Main_Street,_looking_north,_Greenville.jpg) | Public domain | no | Main Street, Greenville · c. 1958 postcard |
| s24 | 1:42.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s25 | 1:44.1 | image | K70 original explainer graphic | Original; fonts OFL | no | Labelled not archival |
| s26 | 1:52.2 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s27 | 1:58.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s28 | 2:02.0 | image | Commons [US068 Washington The Capitol Capitol 1964 (51187727394)](https://commons.wikimedia.org/wiki/File:US068_Washington_The_Capitol_Capitol_1964_(51187727394).jpg) | CC BY 2.0 | yes | U.S. Capitol · c. 1964 |
| s29 | 2:06.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s30 | 2:08.6 | image | Commons [UH-1D helicopters in Vietnam 1966.jpg](https://commons.wikimedia.org/wiki/File:UH-1D_helicopters_in_Vietnam_1966.jpg); Commons [Signing of the EOA.jpg](https://commons.wikimedia.org/wiki/File:Signing_of_the_EOA.jpg); Commons [Apollo 11 Launched Via Saturn V Rocket.jpg](https://commons.wikimedia.org/wiki/File:Apollo_11_Launched_Via_Saturn_V_Rocket.jpg) | Public domain | no |  |
| s31 | 2:12.7 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s32 | 2:17.1 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s33 | 2:19.5 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s34 | 2:24.3 | dataviz | K70 chart (local render); data: U.S. Treasury (Minerals Yearbook 1952) at $35/oz | Original; fonts SIL OFL 1.1 | no |  |
| s35 | 2:29.9 | dataviz | K70 chart (local render); data: U.S. Treasury / U.S. Mint | Original; fonts SIL OFL 1.1 | no | Sourced chart (protected) |
| s36 | 2:34.6 | dataviz | K70 chart (local render); data: U.S. Treasury / U.S. Mint | Original; fonts SIL OFL 1.1 | no |  |
| s37 | 2:38.7 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s38 | 2:43.6 | image | Commons [Bank Run in Michigan, USA, February 1933.jpg](https://commons.wikimedia.org/wiki/File:Bank_Run_in_Michigan,_USA,_February_1933.jpg) | Public domain | no | Bank run · Michigan, February 1933 |
| s39 | 2:46.7 | broll | Pexels video [40350658](https://www.pexels.com/video/40350658/) | Pexels License | no (optional) | OK: abstract architecture |
| s40 | 2:50.0 | broll | Pexels video [39134700](https://www.pexels.com/video/39134700/) | Pexels License | no (optional) | WEAK: printing press for 'Britain asked for three billion more' |
| s41 | 2:53.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s42 | 2:57.5 | image | Commons [Nixon Official Presidential Portrait 07-08-1971 (croppe](https://commons.wikimedia.org/wiki/File:Nixon_Official_Presidential_Portrait_07-08-1971_(cropped).jpg) | Public domain | no | Official portrait · 8 July 1971 |
| s43 | 3:01.5 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s44 | 3:08.1 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s45 | 3:09.3 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s46 | 3:13.1 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s47 | 3:18.0 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s48 | 3:24.6 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s49 | 3:25.4 | broll | Pexels video [39134699](https://www.pexels.com/video/39134699/) | Pexels License | no (optional) | OK: printing press for 'printing money' |
| s50 | 3:28.7 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s51 | 3:33.9 | dataviz | K70 chart (local render); data: BLS CPI-U (40.5 → 215.3) | Original; fonts SIL OFL 1.1 | no |  |
| s52 | 3:38.0 | image | Commons [A button from the "Whip Inflation Now" initiative of th](https://commons.wikimedia.org/wiki/File:A_button_from_the_%22Whip_Inflation_Now%22_initiative_of_the_1970%27s.jpg) | Public domain | no | 'Whip Inflation Now' button · 1974 |
| s53 | 3:43.6 | image | Commons [Gold bars stacked in a pyramid, Dawson, probably betwee](https://commons.wikimedia.org/wiki/File:Gold_bars_stacked_in_a_pyramid,_Dawson,_probably_between_1902_and_1910_(AL%2BCA_1405).jpg) | Public domain | no |  |
| s54 | 3:47.8 | dataviz | K70 chart (local render); data: London gold fixing, 21 January 1980 | Original; fonts SIL OFL 1.1 | no |  |
| s55 | 3:53.9 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s56 | 3:58.4 | image | Commons [SHOPPING FOR GROCERIES IN A WASHINGTON, DISTRICT OF COL](https://commons.wikimedia.org/wiki/File:SHOPPING_FOR_GROCERIES_IN_A_WASHINGTON,_DISTRICT_OF_COLUMBIA_SUPERMARKET_-_NARA_-_555651.jpg) | Public domain | no | Washington, D.C. supermarket · July 1974 |
| s57 | 4:01.8 | dataviz | K70 chart (local render); data: U.S. Bureau of Labor Statistics, CPI-U | Original; fonts SIL OFL 1.1 | no |  |
| s58 | 4:08.3 | image | Commons [1953 - Savings Account Passbook - Allentown National Ba](https://commons.wikimedia.org/wiki/File:1953_-_Savings_Account_Passbook_-_Allentown_National_Bank_-_Allentown_PA.jpg) | Public domain | no | Savings-account passbook · 1953 |
| s59 | 4:12.6 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s60 | 4:18.4 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s61 | 4:22.7 | dataviz | K70 chart (local render); data: Federal Reserve | Original; fonts SIL OFL 1.1 | no |  |
| s62 | 4:25.9 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s63 | 4:31.6 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s64 | 4:33.6 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s65 | 4:38.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s66 | 4:39.5 | dataviz | K70 chart (local render); data: FDIC / GAO (1996) | Original; fonts SIL OFL 1.1 | no |  |
| s67 | 4:47.3 | dataviz | K70 chart (local render); data: U.S. General Accounting Office, 1996 | Original; fonts SIL OFL 1.1 | no | Sourced chart (protected) |
| s68 | 4:50.9 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s69 | 4:54.4 | dataviz | K70 chart (local render); data: Dow Jones Industrial Average | Original; fonts SIL OFL 1.1 | no |  |
| s70 | 5:01.9 | broll | Pexels video [35606045](https://www.pexels.com/video/35606045/) | Pexels License | no (optional) | ANACHRONISTIC: modern tablet trading charts for the 1987 crash; generic |
| s71 | 5:05.6 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s72 | 5:08.2 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s73 | 5:11.6 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s74 | 5:15.8 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s75 | 5:19.3 | broll | Pexels video [38721048](https://www.pexels.com/video/38721048/) | Pexels License | no (optional) | OK: generic tower for LTCM (illustrative) |
| s76 | 5:27.1 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s77 | 5:32.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s78 | 5:33.4 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s79 | 5:36.8 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s80 | 5:44.8 | image | Commons [Bank of Gustine, CA.jpg](https://commons.wikimedia.org/wiki/File:Bank_of_Gustine,_CA.jpg) | CC BY 4.0 | yes | Bank branch, Gustine, California |
| s81 | 5:46.8 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s82 | 5:48.9 | image | Commons [Web Summit 2018 - MoneyConf - Day 2, November 7 HM1 701](https://commons.wikimedia.org/wiki/File:Web_Summit_2018_-_MoneyConf_-_Day_2,_November_7_HM1_7012_(45041353684).jpg) | CC BY 2.0 | yes | David Chaum · Web Summit, Nov 2018 |
| s83 | 5:52.4 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s84 | 5:58.5 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s85 | 6:06.2 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s86 | 6:10.6 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s87 | 6:15.7 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s88 | 6:18.9 | image | K70 original typography | Original; fonts OFL | no |  |
| s89 | 6:21.3 | dataviz | K70 chart (local render); data: Chapter 11 filing, November 1998 | Original; fonts SIL OFL 1.1 | no |  |
| s90 | 6:25.6 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s91 | 6:32.3 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s92 | 6:34.9 | broll | Pexels video [7231661](https://www.pexels.com/video/7231661/) | Pexels License | no (optional) | STEREOTYPE: hooded 'hacker' for cypherpunks; recommend replacement |
| s93 | 6:36.9 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s94 | 6:43.2 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s95 | 6:45.0 | image | Commons [Munitions T-shirt (front).jpg](https://commons.wikimedia.org/wiki/File:Munitions_T-shirt_(front).jpg) | CC0 | no | 'Munitions' T-shirt · crypto code · 1997 |
| s96 | 6:46.2 | image | K70 original explainer graphic | Original; fonts OFL | no | Labelled not archival |
| s97 | 6:53.5 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s98 | 7:02.9 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s99 | 7:06.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s100 | 7:10.5 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s101 | 7:14.2 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s102 | 7:16.6 | broll | Pexels video [5981841](https://www.pexels.com/video/5981841/) | Pexels License | no (optional) | CHECK: very dark frame at 1 s; verify visibility |
| s103 | 7:20.2 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s104 | 7:26.1 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s105 | 7:31.2 | image | Commons [Handcuffs and Key (Taipei New Culture Memorial Hall).jp](https://commons.wikimedia.org/wiki/File:Handcuffs_and_Key_(Taipei_New_Culture_Memorial_Hall).jpg) | CC0 | no | Handcuffs (museum display) |
| s106 | 7:33.1 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s107 | 7:34.5 | image | Commons [Gold bullion bars.jpg](https://commons.wikimedia.org/wiki/File:Gold_bullion_bars.jpg) | CC0 | no | Gold bullion bars (illustrative) |
| s108 | 7:40.4 | image | Commons [Robert F. Kennedy Department of Justice Building.jpg](https://commons.wikimedia.org/wiki/File:Robert_F._Kennedy_Department_of_Justice_Building.jpg) | CC BY 4.0 | yes | U.S. Department of Justice, Washington |
| s109 | 7:44.8 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s110 | 7:47.8 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s111 | 7:49.5 | image | K70 original typography | Original; fonts OFL | no |  |
| s112 | 7:56.5 | image | Commons [Door knocker in Taranto 01.jpg](https://commons.wikimedia.org/wiki/File:Door_knocker_in_Taranto_01.jpg) | CC0 | no |  |
| s113 | 8:02.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s114 | 8:05.2 | image | Commons [Door and Door Frame, Y&A London.jpg](https://commons.wikimedia.org/wiki/File:Door_and_Door_Frame,_Y%26A_London.jpg) | CC0 | no |  |
| s115 | 8:07.0 | image | K70 original explainer graphic | Original; fonts OFL; Natural Earth PD | no | Labelled not archival |
| s116 | 8:08.8 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s117 | 8:12.6 | image | K70 original explainer graphic | Original; fonts OFL | no | Labelled not archival |
| s118 | 8:15.9 | dataviz | K70 chart (local render); data: Decree 1570/2001 (the corralito) | Original; fonts SIL OFL 1.1 | no |  |
| s119 | 8:20.4 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s120 | 8:25.2 | dataviz | K70 chart (local render); data: Republic of Argentina / IMF | Original; fonts SIL OFL 1.1 | no |  |
| s121 | 8:29.1 | image | K70 original explainer graphic | Original; fonts OFL | no | Labelled not archival |
| s122 | 8:33.4 | broll | Pexels video [35834801](https://www.pexels.com/video/35834801/) | Pexels License | no (optional) | OK: generic helicopter (not De la Rúa's) |
| s123 | 8:38.6 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s124 | 8:42.8 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s125 | 8:46.0 | dataviz | K70 chart (local render); data: Hanke & Kwok, Cato Journal 29(2), 2009 | Original; fonts SIL OFL 1.1 | no |  |
| s126 | 8:50.7 | image | K70 original typography | Original; fonts OFL | no |  |
| s127 | 8:55.3 | broll | Pexels video [20573001](https://www.pexels.com/video/20573001/) | Pexels License | no (optional) | OK: bus passenger (generic) |
| s128 | 8:57.2 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s129 | 9:01.5 | image | Commons [Suburban houses near a forest (Unsplash).jpg](https://commons.wikimedia.org/wiki/File:Suburban_houses_near_a_forest_(Unsplash).jpg) | CC0 | no | Suburb, Birmingham, United States · 2016 |
| s130 | 9:05.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s131 | 9:08.0 | threejs | K70 Three.js `globe_flight` (MIT three.js; Natural Earth + US Census borders, PD; canvas textures) | Original / MIT + PD data | no | Preview quality 360×640 upscaled to 1080×1920; re-render at full quality before release |
| s132 | 9:12.3 | image | Commons [Northern Rock Queue.jpg](https://commons.wikimedia.org/wiki/File:Northern_Rock_Queue.jpg) | CC BY 2.0 | yes |  |
| s133 | 9:15.6 | broll | Pexels video [7065835](https://www.pexels.com/video/7065835/) | Pexels License | no (optional) | WEAK: abstract concrete pillar |
| s134 | 9:18.6 | dataviz | K70 chart (local render); data: Overend & Gurney, 1866 → Northern Rock, 2007 | Original; fonts SIL OFL 1.1 | no |  |
| s135 | 9:22.9 | dataviz | K70 chart (local render); data: JPMorgan Chase / Federal Reserve | Original; fonts SIL OFL 1.1 | no |  |
| s136 | 9:29.4 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s137 | 9:34.1 | broll | Pexels video [8480680](https://www.pexels.com/video/8480680/) | Pexels License | no (optional) | OK: trading keyboard |
| s138 | 9:35.9 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s139 | 9:41.0 | broll | Pexels video [37546338](https://www.pexels.com/video/37546338/) | Pexels License | no (optional) | MISLEADING: person writing on an unrelated menu/flyer for Lehman's filing; recommend replacement |
| s140 | 9:47.1 | dataviz | K70 chart (local render); data: Chapter 11 petition, 15 September 2008 | Original; fonts SIL OFL 1.1 | no |  |
| s141 | 9:54.0 | dataviz | K70 chart (local render); data: Federal Reserve Board, 16 September 2008 | Original; fonts SIL OFL 1.1 | no |  |
| s142 | 10:01.0 | dataviz | K70 chart (local render); data: Emergency Economic Stabilization Act, 3 October 2008 | Original; fonts SIL OFL 1.1 | no |  |
| s143 | 10:07.1 | broll | Pexels video [35817535](https://www.pexels.com/video/35817535/) | Pexels License | no (optional) | OK: suburban street |
| s144 | 10:10.0 | dataviz | K70 chart (local render); data: CoreLogic, Foreclosure Crisis Decade in Review (2017) | Original; fonts SIL OFL 1.1 | no |  |
| s145 | 10:15.6 | ai_video | AI still (Pollinations `flux`) + local 2.5D motion (finance_cinematic_f2) | Apache-2.0 model output per third-party sources (FLUX.1 schnell) — UNVERIFIED | no | Synthetic; YouTube 'altered or synthetic content' disclosure required |
| s146 | 10:18.5 | image | Commons [U.S. Treasury building, Washington, D.C LCCN2011631001.](https://commons.wikimedia.org/wiki/File:U.S._Treasury_building,_Washington,_D.C_LCCN2011631001.tif) | Public domain | no | U.S. Treasury Building, Washington |
| s147 | 10:22.6 | image | K70 original explainer graphic | Original; fonts OFL | no | Labelled not archival |
| s148 | 10:26.3 | broll | Pexels video [35195175](https://www.pexels.com/video/35195175/) | Pexels License | no (optional) | WEAK: concert lasers for 'something broke that autumn' |
| s149 | 10:29.6 | image | Commons [Eccles Building (26088200676).jpg](https://commons.wikimedia.org/wiki/File:Eccles_Building_(26088200676).jpg) | Public domain | no | Federal Reserve, Eccles Building · 2011 |
| s150 | 10:34.2 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s151 | 10:38.9 | broll | Pexels video [11318637](https://www.pexels.com/video/11318637/) | Pexels License | no (optional) | OK: city lights aerial |
| s152 | 10:41.0 | broll | Pexels video [35223025](https://www.pexels.com/video/35223025/) | Pexels License | no (optional) | OK: abandoned house |
| s153 | 10:46.1 | broll | Pexels video [19532053](https://www.pexels.com/video/19532053/) | Pexels License | no (optional) | OK: dark room with laptop |
| s154 | 10:49.0 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s155 | 10:52.5 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |
| s156 | 10:54.4 | motion_gfx | K70 kinetic typography (local render) | Original; fonts SIL OFL 1.1 | no |  |

## Historical-accuracy review of stock and stills (frame check)

**Fixed in this revision (replaced with verified PD/CC0 or original graphics):**
- **s5:** Voyager Golden Record → Fort Knox Bullion Depository, 1939.
- **s6:** Trump-era Marine One → Nixon-era Marine One, March 1971 (NARA).
- **s16:** modern German town → 1923 inflation medal (bread = 80 billion marks).
- **s25:** actress at a "hearing" → document graphic for the JEC hearings, 26–30 Oct 1959.
- **s105:** veiled woman paired with "arrested" → handcuffs (CC0).
- **s107:** Bitcoin coins for e-gold (1996) → gold bullion, illustrative (CC0).
- **s147:** UK "Bank Stores" sign (CC BY-SA) → original foreclosure-notice illustration.
- **s149:** uniformed man holding a Bible → Federal Reserve Eccles Building (PD).

**Still flagged (not historically false, but weak or stereotyped):**
- **Recommend replacement:** s92 ("hacker" stereotype) and s139 (unrelated flyer for Lehman's filing).
- **Weak or anachronistic:** s13, s21, s40, s70, s133, s148.
- **Verify visibility:** s102 (dark frame).

## Remaining blockers

1. **AI cinematic (8 clips):** confirm Pollinations output rights and model identity (FLUX.1 schnell vs dev). Six stills were "recovered" from an earlier cache, so their generation date and model are unknown.
2. **Three.js (20 clips):** rendered at preview quality, 360×640. Re-render at full quality before release; the source data licence is fine.
3. **Stock accuracy:** s92 and s139 should be replaced; s13, s21, s40, s70, s133 and s148 are weak.
4. **Editorial:** one 4-card run remains (s97–s100), plus 3-card runs at s43–s45, s63–s65, s83–s85 and s154–s156. Crossfades are at 79/156 (51%).
5. **Full render and human frame-by-frame QA**, not started as instructed.
6. **Credits:** must be pasted into the description; AI disclosure must be ticked at upload.
