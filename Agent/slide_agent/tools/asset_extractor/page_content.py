"""Step 1: read the PDF once into plain data that every finder shares.

All coordinates are PDF points with (0, 0) at the top-left of the page.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pymupdf

# Fonts used for typeset math. Plain Computer Modern text (CMR) is left out on
# purpose: some templates (e.g. LNCS) set the body text in it.
MATH_FONT = re.compile(r"CMMI|CMSY|CMEX|CMBSY|MSAM|MSBM|Math|STIX|Symbol", re.I)
BOLD_FONT = re.compile(r"Bold|Medi|Black|Semibold|CMBX|-Bd", re.I)


@dataclass(eq=False)
class Line:
    """One line of text."""

    page: int  # 1-based
    bbox: pymupdf.Rect
    text: str
    size: float  # largest font size on the line
    bold: bool
    math_ratio: float  # share of characters set in math fonts


@dataclass(eq=False)
class Page:
    number: int  # 1-based
    rect: pymupdf.Rect
    lines: list[Line]
    graphics: list[pymupdf.Rect]  # images and vector drawings (lines, boxes, plots)


@dataclass(eq=False)
class Paper:
    doc: pymupdf.Document
    pages: list[Page]
    body_size: float  # font size of the main text
    columns: list[tuple[float, float]]  # x-range of each text column
    running: set[tuple[int, int]]  # (y0, y1) bands of headers, footers, page numbers: repeated on most pages

    def is_running(self, rect: pymupdf.Rect) -> bool:
        """True for page furniture that repeats at the same height on most pages."""
        return (round(rect.y0), round(rect.y1)) in self.running

    @property
    def text_width(self) -> float:
        return self.columns[-1][1] - self.columns[0][0]

    def is_body(self, line: Line) -> bool:
        """True for main-text lines (as opposed to captions, labels, footnotes)."""
        return line.size >= self.body_size - 0.6

    def column_for(self, rect: pymupdf.Rect, page: "Page | None" = None) -> tuple[float, float]:
        """The column a caption sits in; the full text width if it spans both.

        Pass the page to also catch single-column pages (e.g. an appendix) of a two-column paper.
        """
        full = (self.columns[0][0], self.columns[-1][1])
        if len(self.columns) == 1 or rect.width > 0.6 * (full[1] - full[0]):
            return full
        if page is not None:
            wide = [ln for ln in page.lines if self.is_body(ln) and ln.bbox.width > 0.8 * (full[1] - full[0])]
            if len(wide) >= 3:
                return full
        return self.column_at(rect)

    def column_at(self, rect: pymupdf.Rect) -> tuple[float, float]:
        """The single column that contains the center of rect."""
        center = (rect.x0 + rect.x1) / 2
        return min(self.columns, key=lambda c: 0 if c[0] <= center <= c[1] else min(abs(center - c[0]), abs(center - c[1])))


def read_paper(pdf_path: str) -> Paper:
    doc = pymupdf.open(pdf_path)
    pages = [_read_page(page) for page in doc]

    all_lines = [line for page in pages for line in page.lines]
    if not all_lines:
        raise ValueError(f"{pdf_path} has no extractable text (scanned PDF?).")

    body_size = _body_size(all_lines)
    body = [
        line for line in all_lines
        if abs(line.size - body_size) <= 0.3 and len(line.text) >= 30
        and line.bbox.width >= 120 and line.math_ratio < 0.2
    ]
    if not body:
        raise ValueError(f"Could not find the main text of {pdf_path}.")

    return Paper(
        doc=doc,
        pages=pages,
        body_size=body_size,
        columns=_detect_columns(body),
        running=_running_bands(pages, body_size),
    )


def _running_bands(pages: list[Page], body_size: float) -> set[tuple[int, int]]:
    """Find headers, footers and page numbers: things at the same height on at least half the pages.

    Running text lines are small print or short ("12"); body lines also start at the
    same height on every page, so they are not counted.
    """
    seen: dict[tuple[int, int], set[int]] = {}
    for page in pages:
        rects = list(page.graphics)
        rects += [
            line.bbox for line in page.lines
            if line.size < body_size - 0.6 or len(line.text) <= 6
        ]
        for rect in rects:
            seen.setdefault((round(rect.y0), round(rect.y1)), set()).add(page.number)
    need = max(3, 0.5 * len(pages))
    return {band for band, on_pages in seen.items() if len(on_pages) >= need}


def _read_page(page: pymupdf.Page) -> Page:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for raw in block.get("lines", []):
            spans = [s for s in raw["spans"] if s["text"].strip()]
            if not spans or abs(raw["dir"][1]) > 0.1:  # skip empty and rotated text
                continue
            text = unicodedata.normalize("NFKC", "".join(s["text"] for s in raw["spans"])).strip()
            chars = sum(len(s["text"]) for s in spans)
            math_chars = sum(len(s["text"]) for s in spans if MATH_FONT.search(s["font"]))
            lines.append(Line(
                page=page.number + 1,
                bbox=pymupdf.Rect(raw["bbox"]),
                text=text,
                size=max(s["size"] for s in spans),
                bold=bool(BOLD_FONT.search(spans[0]["font"])),
                math_ratio=math_chars / chars,
            ))
    return Page(page.number + 1, page.rect, lines, _read_graphics(page))


def _read_graphics(page: pymupdf.Page) -> list[pymupdf.Rect]:
    rects = [pymupdf.Rect(info["bbox"]) for info in page.get_image_info()]
    rects += [pymupdf.Rect(d["rect"]) for d in page.get_drawings()]
    graphics = []
    for rect in rects:
        if max(rect.width, rect.height) < 3 or rect.get_area() > 0.85 * page.rect.get_area():
            continue  # specks, and page-sized backgrounds
        # hairlines (table rules) have no area; give them a little thickness
        rect = pymupdf.Rect(rect.x0 - 0.5, rect.y0 - 0.5, rect.x1 + 0.5, rect.y1 + 0.5) & page.rect
        if not rect.is_empty:
            graphics.append(rect)
    return graphics


def _body_size(lines: list[Line]) -> float:
    chars_per_size = Counter()
    for line in lines:
        chars_per_size[round(line.size, 1)] += len(line.text)
    return chars_per_size.most_common(1)[0][0]


def _detect_columns(body: list[Line]) -> list[tuple[float, float]]:
    """Find the text columns from the left/right edges shared by many body lines."""
    lefts = _frequent([round(line.bbox.x0) for line in body])
    rights = _frequent([round(line.bbox.x1) for line in body])
    text_left, text_right = min(lefts), max(rights)
    for edge in sorted(rights):
        if edge < text_left + 0.65 * (text_right - text_left):  # a right edge in the left half: two columns
            right_starts = [x for x in lefts if x > edge + 5]
            if right_starts:
                return [(text_left, edge), (min(right_starts), text_right)]
    return [(text_left, text_right)]


def _frequent(values: list[int], share: float = 0.05) -> list[int]:
    need = max(5, share * len(values))
    return [value for value, count in Counter(values).items() if count >= need]
