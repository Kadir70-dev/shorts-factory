"""
Scribus-side runner. Executed BY Scribus's embedded interpreter
(`scribus -g -cl -py _runner.py -- plan.json result.json`), never imported by
the FastAPI process — the `scribus` module only exists inside that process.

Data-driven on purpose: one script, exercised once and never touched again,
versus regenerating bespoke Scribus API calls per template. A layout bug is
then a `layout.py`/`templates.py` bug, not a "does this generated script have
a typo" bug.
"""
import json
import sys
import traceback


def main() -> None:
    plan_path, result_path = sys.argv[-2], sys.argv[-1]
    result = {"ok": False, "error": "", "colors_defined": 0, "frames": 0}
    try:
        import scribus

        with open(plan_path, "r", encoding="utf-8") as fh:
            plan = json.load(fh)

        page = plan["page"]
        scribus.newDocument(
            (page["width"], page["height"]),
            tuple(page["margins"]),
            scribus.PORTRAIT,
            1,
            scribus.UNIT_POINTS,
            scribus.PAGE_1,
            0,
            1,
        )

        # Page background: a full-bleed filled rect behind everything else,
        # since Scribus documents default to a transparent/white canvas and
        # aged-paper tones are part of the design, not a post-effect.
        bg = plan.get("background")
        if bg and bg.lower() != "#ffffff":
            name = _define_color(scribus, bg)
            r = scribus.createRect(0, 0, page["width"], page["height"], "bg_plate")
            scribus.setFillColor(name, r)
            scribus.setLineColor(name, r)

        defined: dict[str, str] = {}

        for i, f in enumerate(plan["frames"]):
            kind = f["kind"]
            fname = f.get("name") or f"{kind}{i}"

            if kind == "text":
                obj = scribus.createText(f["x"], f["y"], f["w"], f["h"], fname)
                text = f["text"].upper() if f.get("upper") else f["text"]
                scribus.setText(text, obj)
                scribus.setFont(f.get("font", "Times New Roman Regular"), obj)
                scribus.setFontSize(float(f.get("size", 12.0)), obj)
                align = {
                    "left": scribus.ALIGN_LEFT, "right": scribus.ALIGN_RIGHT,
                    "center": scribus.ALIGN_CENTERED, "justify": scribus.ALIGN_BLOCK,
                }[f.get("align", "left")]
                scribus.setTextAlignment(align, obj)
                color_name = _cached_color(scribus, defined, f.get("color", "#000000"))
                scribus.setTextColor(color_name, obj)
                if f.get("line_spacing"):
                    scribus.setLineSpacing(float(f["line_spacing"]), obj)
                if f.get("tracking"):
                    scribus.setTracking(float(f["tracking"]), obj)
                if f.get("rotation"):
                    scribus.rotateObjectAbs(float(f["rotation"]), obj)

            elif kind == "image":
                obj = scribus.createImage(f["x"], f["y"], f["w"], f["h"], fname)
                path = f.get("image_path", "")
                if path:
                    scribus.loadImage(path, obj)
                    scribus.setScaleImageToFrame(True, True, obj)
                if f.get("rotation"):
                    scribus.rotateObjectAbs(float(f["rotation"]), obj)

            elif kind == "rect":
                obj = scribus.createRect(f["x"], f["y"], f["w"], f["h"], fname)
                if f.get("fill_color"):
                    scribus.setFillColor(
                        _cached_color(scribus, defined, f["fill_color"]), obj)
                else:
                    scribus.setFillColor("None", obj)
                if f.get("line_color"):
                    scribus.setLineColor(
                        _cached_color(scribus, defined, f["line_color"]), obj)
                    scribus.setLineWidth(float(f.get("line_width", 0.5)), obj)
                else:
                    scribus.setLineColor("None", obj)
                if f.get("rotation"):
                    scribus.rotateObjectAbs(float(f["rotation"]), obj)

            elif kind == "line":
                obj = scribus.createLine(f["x"], f["y"], f["x"] + f["w"],
                                         f["y"] + f["h"], fname)
                scribus.setLineColor(
                    _cached_color(scribus, defined, f.get("line_color", "#000000")), obj)
                scribus.setLineWidth(float(f.get("line_width", 0.5)), obj)

            result["frames"] += 1

        result["colors_defined"] = len(defined)

        out = plan["outputs"]
        if out.get("sla"):
            scribus.saveDocAs(out["sla"])

        if out.get("pdf"):
            pdf = scribus.PDFfile()
            pdf.file = out["pdf"]
            pdf.fontEmbedding = 0     # 0 = embed fully/subset (per PDFfile docs)
            pdf.save()

        if out.get("png"):
            ie = scribus.ImageExport()
            ie.type = "PNG"
            ie.scale = float(out.get("png_scale_pct", 300))
            ie.saveAs(out["png"])

        result["ok"] = True

    except Exception as exc:  # noqa: BLE001 — must reach the result file
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    finally:
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
        try:
            import scribus
            scribus.fileQuit()
        except Exception:  # noqa: BLE001
            pass


def _define_color(scribus_mod, hex_color: str) -> str:
    name = "c" + hex_color.lstrip("#").upper()
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    scribus_mod.defineColorRGB(name, r, g, b)
    return name


def _cached_color(scribus_mod, cache: dict, hex_color: str) -> str:
    if hex_color not in cache:
        cache[hex_color] = _define_color(scribus_mod, hex_color)
    return cache[hex_color]


main()
