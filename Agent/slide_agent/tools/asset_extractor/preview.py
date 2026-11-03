"""Contact sheets: all crops of a paper on a few images, to check them by eye."""

from pathlib import Path

from PIL import Image, ImageDraw

from ...schemas import AssetManifest

TILE = (420, 330)  # thumbnail box (width, height)
LABEL_HEIGHT = 22
COLUMNS = 4
PER_SHEET = 12


def make_contact_sheets(manifest: AssetManifest, out_dir: str | Path) -> list[Path]:
    """Write preview_1.jpg, preview_2.jpg ... (12 crops each) next to assets.json."""
    out_dir = Path(out_dir)
    paths = []
    for start in range(0, len(manifest.assets), PER_SHEET):
        chunk = manifest.assets[start:start + PER_SHEET]
        rows = -(-len(chunk) // COLUMNS)
        sheet = Image.new("RGB", (COLUMNS * TILE[0], rows * (TILE[1] + LABEL_HEIGHT)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, asset in enumerate(chunk):
            x, y = (i % COLUMNS) * TILE[0], (i // COLUMNS) * (TILE[1] + LABEL_HEIGHT)
            image = Image.open(out_dir / asset.image_path).convert("RGB")
            image.thumbnail((TILE[0] - 8, TILE[1] - 8))
            sheet.paste(image, (x + 4, y + LABEL_HEIGHT + 4))
            draw.rectangle([x, y, x + TILE[0] - 1, y + TILE[1] + LABEL_HEIGHT - 1], outline="#bbbbbb")
            draw.text((x + 6, y + 5), f"{asset.id}  (p{asset.page}{', appendix' if asset.in_appendix else ''})", fill="red")
        path = out_dir / f"preview_{start // PER_SHEET + 1}.jpg"
        sheet.save(path, quality=85)
        paths.append(path)
    return paths
