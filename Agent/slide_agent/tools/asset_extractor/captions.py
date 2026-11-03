"""Step 2: find the captions ("Figure 2.", "Table 1:", "Algorithm 1:").

A caption is the anchor for a figure, table or algorithm: regions.py then looks
for the graphic next to it.
"""

import re
from dataclasses import dataclass

import pymupdf

from .page_content import Line, Paper

# "Figure 2." / "Fig. 2:" / "Table 1:" / "Algorithm 1:" at the start of a line.
CAPTION = re.compile(r"^(Figure|Fig\.|Table|Algorithm)\s*([A-Z]?\d+)\s*[:.|]", re.I)
# "Algorithm 1 Title" (no colon, bold) as typeset by the algorithm package; a body sentence is never bold.
ALGORITHM_TITLE = re.compile(r"^(Algorithm)\s*(\d+)\s+(?=\S)", re.I)
KIND = {"figure": "figure", "fig.": "figure", "table": "table", "algorithm": "algorithm"}


@dataclass(eq=False)
class Caption:
    kind: str  # "figure" | "table" | "algorithm"
    number: str  # "2", "A1"
    page: int  # 1-based
    bbox: pymupdf.Rect
    text: str  # caption text without the "Figure 2." label
    size: float = 0.0  # font size of the first line


def find_captions(paper: Paper) -> list[Caption]:
    captions = []
    for page in paper.pages:
        for i, line in enumerate(page.lines):
            match = CAPTION.match(line.text) or (line.bold and ALGORITHM_TITLE.match(line.text))
            if not match:
                continue
            lines = _caption_lines(page.lines, i, page.graphics)
            text = " ".join(line.text for line in lines)
            bbox = lines[0].bbox
            for line in lines[1:]:
                bbox = bbox | line.bbox
            caption = Caption(
                kind=KIND[match.group(1).lower()],
                number=match.group(2).upper(),
                page=page.number,
                bbox=bbox,
                text=text[match.end():].strip(),
                size=line.size,
            )
            captions.append(caption)
    return captions


def real_captions(captions: list[Caption], regions: dict) -> list[Caption]:
    """Keep one caption per (kind, number, page).

    A body sentence can start with "Table 2. It is observed that ..." and then looks like a
    second caption. The real one is the one with a figure or table next to it; if both have,
    the one in the smaller caption font.
    """
    best: dict[tuple, Caption] = {}
    for caption in captions:
        key = (caption.kind, caption.number, caption.page)
        rank = lambda c: (regions[c] is None, c.size)
        if key not in best or rank(caption) < rank(best[key]):
            best[key] = caption
    return [c for c in captions if best[(c.kind, c.number, c.page)] is c]


def _caption_lines(lines: list[Line], start: int, graphics: list[pymupdf.Rect]) -> list[Line]:
    """The first caption line plus the lines that continue the same paragraph."""
    first = lines[start]
    caption = [first]
    row = pymupdf.Rect(first.bbox)  # the caption row being read (a row can be several PDF lines, see below)
    first_row_right = None  # right edge of the first row, once it is complete
    for nxt in lines[start + 1:]:
        if CAPTION.match(nxt.text):
            break
        if _continues_row(nxt, row):  # "Figure 1." and the text after it are often separate lines on one row
            caption.append(nxt)
            row |= nxt.bbox
            continue
        if first_row_right is None:
            first_row_right = row.x1
        continues = (
            abs(nxt.size - first.size) <= 0.3  # same font size
            and abs(nxt.bbox.x0 - first.bbox.x0) <= 6  # same left edge
            and nxt.bbox.y0 > row.y0  # below the previous row
            and nxt.bbox.y0 - row.y1 <= 0.5 * first.size  # little white space between the rows (a dagger can make a row taller)
            and row.x1 >= first_row_right - 12  # the previous row ran to the right edge
        )
        if not continues or _rule_between(row, nxt.bbox, graphics):
            break
        caption.append(nxt)
        row = pymupdf.Rect(nxt.bbox)
    return caption


def _rule_between(upper: pymupdf.Rect, lower: pymupdf.Rect, graphics: list[pymupdf.Rect]) -> bool:
    """True if a horizontal rule runs between the two rows: an algorithm's title ends at its rule."""
    return any(
        g.height < 3 and g.width >= 0.5 * upper.width and upper.y1 - 1 <= g.y0 and g.y1 <= lower.y0 + 1
        for g in graphics
    )


def _continues_row(line: Line, row: pymupdf.Rect) -> bool:
    """True if line sits on the same row as row, just to its right."""
    overlap = min(line.bbox.y1, row.y1) - max(line.bbox.y0, row.y0)
    gap = line.bbox.x0 - row.x1  # slightly negative when a math glyph makes the boxes overlap
    return overlap >= 0.5 * min(line.bbox.height, row.height) and -15 <= gap <= 20 and line.bbox.x1 > row.x1
