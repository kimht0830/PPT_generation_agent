"""extract_assets: crop every figure, table, algorithm and equation out of a paper PDF.

Pipeline (one module per step):
    page_content  read the PDF into lines + graphics + layout
    captions      find "Figure 2." / "Table 1:" / "Algorithm 1:" captions
    regions       from a caption, find the figure/table/algorithm next to it
    equations     find numbered display equations
    sections      headings, appendix start, which sections mention which asset
    extractor     (this file) crop the regions to PNG and write assets.json
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ...schemas import Asset, AssetManifest, ExtractionSettings
from .captions import find_captions, real_captions
from .equations import find_equations
from .page_content import read_paper
from .regions import find_regions
from .sections import find_appendix_start, find_headings, find_mentions

ALL_KINDS = ("figure", "table", "algorithm", "equation")
ID_PREFIX = {"figure": "fig", "table": "tab", "algorithm": "alg", "equation": "eq"}
CROP_PADDING = {"figure": 3, "table": 3, "algorithm": 3, "equation": 2}  # points of white space kept around each crop


@dataclass
class Found:
    """An asset located in the PDF, before it is cropped."""

    kind: str
    number: str
    page: int
    bbox: pymupdf.Rect
    caption: str


def extract_assets(
    pdf_path: str | Path,
    out_dir: str | Path,
    kinds: tuple[str, ...] = ALL_KINDS,
    include_appendix: bool = True,
    dpi: int = 300,
) -> AssetManifest:
    """Crop the assets of one paper into out_dir/assets/*.png and write out_dir/assets.json."""
    out_dir = Path(out_dir)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)

    paper = read_paper(str(pdf_path))
    headings = find_headings(paper)
    appendix_start = find_appendix_start(headings)
    captions = find_captions(paper)

    caption_boxes: dict[int, list[pymupdf.Rect]] = {}
    for caption in captions:
        caption_boxes.setdefault(caption.page, []).append(caption.bbox)
    mentions = find_mentions(paper, caption_boxes)

    warnings: list[str] = []
    found: list[Found] = []
    regions: dict = {}
    for page in paper.pages:
        on_page = [c for c in captions if c.page == page.number]
        if on_page:
            regions.update(find_regions(on_page, paper))

    for caption in real_captions(captions, regions):
        if caption.kind not in kinds:
            continue
        region = regions[caption]
        if region is None:
            warnings.append(f"{caption.kind.title()} {caption.number} (page {caption.page}): caption found but no graphic next to it")
            continue
        found.append(Found(caption.kind, caption.number, caption.page, region, caption.text))

    if "equation" in kinds:
        # A "(1)" inside a figure or table (e.g. a column header) is not an equation.
        boxes = [(f.page, f.bbox) for f in found]
        for eq in find_equations(paper):
            center = pymupdf.Point((eq.bbox.x0 + eq.bbox.x1) / 2, (eq.bbox.y0 + eq.bbox.y1) / 2)
            if not any(page == eq.page and box.contains(center) for page, box in boxes):
                found.append(Found("equation", eq.number, eq.page, eq.bbox, eq.context))

    found.sort(key=lambda f: (f.page, f.bbox.y0, f.bbox.x0))

    assets: list[Asset] = []
    used_ids: set[str] = set()
    for item in found:
        in_appendix = appendix_start is not None and (item.page, item.bbox.y0) >= appendix_start
        if in_appendix and not include_appendix:
            continue
        asset_id = _unique_id(ID_PREFIX[item.kind], item.number, used_ids, in_appendix)
        image_path = f"assets/{asset_id}.png"
        crop, size_px = _render(paper.doc[item.page - 1], item, CROP_PADDING[item.kind], out_dir / image_path, dpi, caption_boxes.get(item.page, []))
        assets.append(Asset(
            id=asset_id,
            kind=item.kind,
            number=item.number,
            page=item.page,
            bbox=tuple(round(v, 1) for v in crop),
            caption=item.caption,
            image_path=image_path,
            size_px=size_px,
            in_appendix=in_appendix,
            mentioned_in=mentions.get((item.kind, item.number), []),
        ))

    warnings += _consistency_warnings(assets, mentions, kinds)
    manifest = AssetManifest(
        pdf=Path(pdf_path).name,
        settings=ExtractionSettings(kinds=list(kinds), include_appendix=include_appendix, dpi=dpi),
        num_pages=len(paper.pages),
        appendix_start_page=appendix_start[0] if appendix_start else None,
        assets=assets,
        warnings=warnings,
    )
    (out_dir / "assets.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def _unique_id(prefix: str, number: str, used: set[str], in_appendix: bool) -> str:
    """fig_2, tab_1, eq_3 ... Appendix items that reuse a main-text number get a suffix."""
    base = f"{prefix}_{number}"
    candidate = base
    if candidate in used:
        candidate = f"{base}_app" if in_appendix else f"{base}_dup"
    n = 2
    while candidate in used:
        candidate = f"{base}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _render(page: pymupdf.Page, item: Found, pad: float, path: Path, dpi: int, captions: list[pymupdf.Rect]):
    bbox = item.bbox
    crop = pymupdf.Rect(bbox.x0 - pad, bbox.y0 - pad, bbox.x1 + pad, bbox.y1 + pad) & page.rect
    for caption in captions:  # padding must not pull in a caption line (its own or its neighbour's)
        if not crop.intersects(caption):
            continue
        if caption.y0 >= bbox.y1 - 1:  # caption below
            crop.y1 = min(crop.y1, caption.y0 - 2)
        elif caption.y1 <= bbox.y0 + 1:  # caption above
            crop.y0 = max(crop.y0, caption.y1 + 2)
    pixmap = page.get_pixmap(clip=crop, dpi=dpi, alpha=False)
    pixmap.save(path)
    return crop, (pixmap.width, pixmap.height)


def _consistency_warnings(assets: list[Asset], mentions: dict, kinds: tuple[str, ...]) -> list[str]:
    """Cheap self-checks: things the text talks about that we did not extract."""
    warnings = []
    extracted = {(a.kind, a.number) for a in assets}
    for (kind, number), sections in sorted(mentions.items()):
        if kind in kinds and (kind, number) not in extracted:
            warnings.append(f"{kind.title()} {number} is mentioned in the text but was not extracted")

    numbers = sorted(int(re.match(r"\d+", a.number).group()) for a in assets if a.kind == "equation" and not a.in_appendix)
    if numbers:
        missing = sorted(set(range(1, numbers[-1] + 1)) - set(numbers))
        if missing:
            warnings.append(f"Equation numbers not found in the main text: {missing}")
    return warnings
