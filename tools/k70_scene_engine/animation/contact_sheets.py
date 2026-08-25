from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3] / "data/benchmarks/local_animation_stack"


def build(kind: str, frames=(1, 18, 30, 42, 48)) -> Path:
    folder = ROOT / f"test_{kind.lower()}" / "frames"
    paths = [folder / f"frame_{frame:04d}.png" for frame in frames]
    images = [Image.open(path).convert("RGB") for path in paths if path.exists()]
    sheet = Image.new("RGB", (480 * len(images), 300), "#101216"); draw = ImageDraw.Draw(sheet)
    for i, (im, frame) in enumerate(zip(images, frames)):
        sheet.paste(im.resize((480, 270)), (i * 480, 0)); draw.text((i * 480 + 8, 276), f"frame {frame}", fill="white")
    out = ROOT / f"test_{kind.lower()}" / "contact_sheet.jpg"; sheet.save(out, quality=92)
    for im in images: im.close()
    return out


if __name__ == "__main__":
    for name in "ABC": print(build(name))
