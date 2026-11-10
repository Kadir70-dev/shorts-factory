# Automan Star • Azizi Florence 9:16 Reels campaign

This is an **additive, opt-in real-estate ad compositor** for the K70 shorts-factory repository; it does **not** modify or run the existing US-politics/finance Shorts machinery. It uses a structured scene manifest, real approved project imagery, kinetic copy, a real animated price counter, a navy/gold brand treatment, and optional English voiceover audio. Outputs 30s and 15s H.264 Instagram/Facebook Reels creative.

The **live Automan property page** is the source of the broker-advertised facts: https://automanstarrealty.com/properties/azizi-florence . This project is in **Um Fanain, Sharjah**, not Dubai. **AED 2.09M refers to the broker's indicated project starting price; it is NOT a guaranteed price for a villa**. Developer rendering, pricing, availability and payment-plan information are expressly subject to confirmation. No unsupported ROI, payment plan, handover date, shortages, or guaranteed results are asserted.

## Before using imagery in paid advertising

1. Obtain written proof Automan is authorized to use and adapt the **nine developer renders in commercial social media ads**, including voiceover, text overlays and crops. The publicly readable image URLs are listed as provenance in `examples/azizi-florence.json` but **no image is downloaded automatically**, and **none are redistributed in this repo**.
2. Place legitimately obtained/licensed files in `assets/` with the *exact filenames* in the manifest. Do not insert generic villa footage as though it depicts Azizi Florence.
3. Have the broker confirm **latest unit-specific pricing and availability**, review the advertised *from* figure, and obtain the relevant **Sharjah real-estate advertising clearance and any UAE/Dubai permits or agency identifiers** required for this specific ad and account. No invented permit numbers.
4. Confirm Automan has permission to use the brand name and project materials. Legal/regulatory checks must be done by the broker or qualified adviser.
5. If voiceover is needed, supply a properly licensed/released master audio file. No third-party voice clone or copyrighted music is bundled.

## Install

Requires Python 3.10+, Pillow, FFmpeg + ffprobe, and a font such as Lato:

```bash
python -m pip install Pillow
# Place licensed source images into ./assets using the names from the manifest.
python scripts/real_estate_ads/render.py \
  --assets-dir ./assets --output ./previews/azizi-florence-30-draft.mp4
python scripts/real_estate_ads/render.py \
  --assets-dir ./assets --duration 15 --output ./previews/azizi-florence-15-draft.mp4
```

**Dry-run quality smoke test** (only with synthetic fixture images, never as final marketing material):

```bash
python scripts/real_estate_ads/tests/test_real_estate_ads.py
```

For faster draft QA, pass `--preview-scale 0.5`. Normal mode exports 1080×1920 at 30 fps. Provide `--voiceover ./voiceover.wav` to embed narration; otherwise output includes silent AAC. Compositing is always offline and asset-provenance-locked.

To remove the preview watermark, all three clearance flags are required:

```bash
python scripts/real_estate_ads/render.py --assets-dir ./assets \
  --output ./exports/azizi-florence-30.mp4 --public \
  --confirm-render-rights --confirm-current-price \
  --permit-id 'THE-REAL-APPROVED-AD-PERMIT-REFERENCE'
```

**Never use the example permit text as an actual permit.** The flags are manual operator assertions, not verification by this software. The `--public` option only removes the DRAFT overlay; it does not publish to Meta, verify documents, or grant authorization.

## Reels/ad placement

- Format: 1080×1920, H.264, 30 fps, 15 or 30 seconds, MP4.
- CTA: Register interest on official Automan property page or an approved Meta Instant Form. Do not send leads to placeholder phone numbers.
- Required content cues: **Azizi Florence • Sharjah**, **Developer renders (illustrative)**, **price subject to developer confirmation**, Automan Star branding and applicable permit/license information.
- The earlier script's “Still renting?” hook and “Payment plan verified” claim were removed: neither is proven on this property page, and personal financial assumptions are an unnecessary ad-policy risk.
- For Meta housing-category settings and UAE property-ad permits, the media buying account owner must review the actual region/campaign settings and official authority requirements. Target broadly; do not restrict demographic groups unfairly.

## Important limitation

This produces **draft creative from user-supplied images**. Source media files cannot be downloaded or licensed by the assistant on the user's behalf. Actual ad submission and final legal/brand approval are **not** performed by this tool.