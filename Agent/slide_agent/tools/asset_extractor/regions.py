"""Step 3: from a caption, find the figure / table / algorithm it belongs to.

Idea: a figure is a cluster of graphics (images, plot lines, table rules) and
small text (axis labels, table cells) that touches the caption. Starting at the
caption we walk up (or down) and keep adding parts as long as the white space
between them is small and no paragraph of body text is in the way.
"""

import pymupdf

from .captions import Caption
from .page_content import Page, Paper

MAX_GAP = 18  # largest white space (pt) allowed inside one figure or table
TIE_GAP = 4  # two sides whose gaps to the caption differ by less than this (pt) count as equally near
CAPTION_GAP = 30  # largest white space (pt) between a caption and the figure or table it belongs to

# Which side of its caption each kind usually sits on; used when both sides have something.
DEFAULT_SIDE = {"figure": "above", "table": "below", "algorithm": "below"}


def find_regions(page_captions: list[Caption], paper: Paper) -> dict[Caption, pymupdf.Rect | None]:
    """The asset (without its caption) belonging to each caption of one page; None if there is none."""
    page = paper.pages[page_captions[0].page - 1]
    caption_boxes = [c.bbox for c in page_captions]
    regions: dict[Caption, pymupdf.Rect | None] = {}
    sides: dict[Caption, dict[str, pymupdf.Rect | None]] = {}  # what lies above / below each caption
    chosen_side: dict[Caption, str | None] = {}

    for caption in page_captions:
        column = _narrow_to_neighbours(paper.column_for(caption.bbox, page), caption, page_captions)
        if caption.kind == "algorithm":
            box = _ruled_box(caption.bbox, page, column, caption_boxes)
            if box is not None:
                regions[caption] = _add_enclosed_text(box, page, caption_boxes)
                continue
        sides[caption] = _both_sides(caption, page, paper, column, caption_boxes)
        chosen_side[caption] = _choose_side(caption, sides[caption])
        regions[caption] = sides[caption][chosen_side[caption]][0] if chosen_side[caption] else None

    _separate_stacked(page_captions, regions, sides, chosen_side, page, paper, caption_boxes)
    return regions


def _narrow_to_neighbours(column: tuple[float, float], caption: Caption, page_captions: list[Caption]) -> tuple[float, float]:
    """Captions side by side (two tables in one row) each get the half of the width up to the midpoint between them."""
    left, right = column
    for other in page_captions:
        if other is caption:
            continue
        shares_row = min(caption.bbox.y1, other.bbox.y1) - max(caption.bbox.y0, other.bbox.y0) >= 5
        if not shares_row:
            continue
        if other.bbox.x0 >= caption.bbox.x1 - 2:  # neighbour on the right
            right = min(right, (caption.bbox.x1 + other.bbox.x0) / 2)
        elif other.bbox.x1 <= caption.bbox.x0 + 2:  # neighbour on the left
            left = max(left, (other.bbox.x1 + caption.bbox.x0) / 2)
    return left, right


def _both_sides(caption: Caption, page: Page, paper: Paper, column: tuple[float, float], caption_boxes: list[pymupdf.Rect]) -> dict:
    """{"above": (region, gap) or None, "below": (region, gap) or None}."""
    parts = _parts(page, paper, column, caption_boxes)
    barriers = _paragraphs(page, paper, column, caption_boxes)
    others = [b for b in caption_boxes if b != caption.bbox and b.x0 < column[1] and b.x1 > column[0]]  # captions in this column
    result = {}
    for side, upward in (("above", True), ("below", False)):
        grown = _grow(caption.bbox, parts, barriers, upward=upward)
        if grown is None:
            result[side] = None
            continue
        region = _include_straddlers(_add_enclosed_text(grown[0], page, caption_boxes), parts, column, caption_boxes)
        if upward:  # the region must not reach into the caption itself
            region.y1 = min(region.y1, caption.bbox.y0)
        else:
            region.y0 = max(region.y0, caption.bbox.y1)
        if _caption_between(caption.bbox, region, others, upward):
            result[side] = None  # that graphic belongs to the caption standing in front of it
            continue
        result[side] = (region, grown[1])
    return result


def _caption_between(caption: pymupdf.Rect, region: pymupdf.Rect, others: list[pymupdf.Rect], upward: bool) -> bool:
    """True if another caption sits between this caption and the region on that side."""
    for other in others:
        if upward and region.y1 <= other.y0 + 2 and other.y1 <= caption.y0 + 2:
            return True
        if not upward and caption.y1 <= other.y0 + 2 and other.y1 <= region.y0 + 2:
            return True
    return False


def _choose_side(caption: Caption, sides: dict) -> str | None:
    """The nearer side; on a tie, the usual side for this kind."""
    above, below = sides["above"], sides["below"]
    if above and below:
        if abs(above[1] - below[1]) < TIE_GAP:  # gaps differ by a few points only: go by the usual side
            return DEFAULT_SIDE[caption.kind]
        return "above" if above[1] < below[1] else "below"
    return "above" if above else "below" if below else None


def _separate_stacked(captions, regions, sides, chosen_side, page, paper, caption_boxes) -> None:
    """Two assets stacked in one column can both claim the whole stack.

    Example: a table (caption above it) directly over a figure (caption below it).
    The upper caption looks down, the lower one looks up, and both get everything.
    Fix: the caption that has something on its other side takes that; if neither
    has, cut the stack at its widest white space.
    """
    ordered = sorted((c for c in captions if c in sides and regions[c] is not None), key=lambda c: c.bbox.y0)
    for i, upper in enumerate(ordered):
        for lower in ordered[i + 1:]:
            if not (_same_rect(regions[upper], regions[lower]) and chosen_side[upper] == "below" and chosen_side[lower] == "above"):
                continue
            taken = lambda option, me: option is not None and any(
                other is not me and regions[other] is not None and _same_rect(regions[other], option[0]) for other in regions
            )  # the other side already belongs to a third caption
            if sides[upper]["above"] and not taken(sides[upper]["above"], upper):
                chosen_side[upper] = "above"
                regions[upper] = sides[upper]["above"][0]
            elif sides[lower]["below"] and not taken(sides[lower]["below"], lower):
                chosen_side[lower] = "below"
                regions[lower] = sides[lower]["below"][0]
            else:
                halves = _cut_at_widest_gap(regions[upper], page, paper, caption_boxes)
                if halves:
                    regions[upper], regions[lower] = halves


def _same_rect(a: pymupdf.Rect, b: pymupdf.Rect) -> bool:
    return all(abs(x - y) < 1 for x, y in zip(a, b))


def _cut_at_widest_gap(region: pymupdf.Rect, page: Page, paper: Paper, caption_boxes: list[pymupdf.Rect]):
    """(upper half, lower half) of region, cut where the white space is widest; None if there is no gap."""
    column = paper.column_for(region, page)
    parts = sorted(
        (p for p in _parts(page, paper, column, caption_boxes) if region.contains(p)),
        key=lambda p: p.y0,
    )
    widest, cut = 0.0, None
    bottom = parts[0].y1 if parts else 0
    for part in parts[1:]:
        if part.y0 - bottom > widest:
            widest, cut = part.y0 - bottom, (bottom, part.y0)
        bottom = max(bottom, part.y1)
    if cut is None:
        return None
    upper = pymupdf.Rect(region.x0, region.y0, region.x1, cut[0])
    lower = pymupdf.Rect(region.x0, cut[1], region.x1, region.y1)
    return upper, lower


def _ruled_box(caption_box: pymupdf.Rect, page: Page, column: tuple[float, float], caption_boxes: list[pymupdf.Rect]) -> pymupdf.Rect | None:
    """An algorithm is a box framed by wide horizontal rules; its caption is the title above the first one.

    Starting at the rule just under the caption, keep taking the next wide rule
    until another caption gets in the way. The box is everything between.
    """
    min_width = 0.8 * (column[1] - column[0])
    in_column = lambda g: column[0] - 3 <= (g.x0 + g.x1) / 2 <= column[1] + 3  # not a rule of the other column
    wide_rules = [g for g in page.graphics if g.height < 3 and g.width >= min_width and in_column(g)]
    rules = sorted((g for g in wide_rules if g.y0 >= caption_box.y1 - 2), key=lambda g: g.y0)
    if not rules or rules[0].y0 - caption_box.y1 > 20:
        return None
    box = rules[0]
    # A rule just above the caption means the title is part of the box (the usual algorithm style):
    # take the title and that rule too. Without one the title stands outside the box and is left out.
    title_rule = [g for g in wide_rules if 0 <= caption_box.y0 - g.y1 <= 8 and g.x0 < caption_box.x1 and g.x1 > caption_box.x0]
    if title_rule:
        box = box | title_rule[0] | caption_box
    for rule in rules[1:]:
        other_caption_between = any(
            b.y0 > box.y1 and b.y1 < rule.y0 and b.x0 < column[1] and b.x1 > column[0]  # in this column
            for b in caption_boxes if b != caption_box
        )
        if rule.y0 - box.y1 > 450 or other_caption_between:
            break
        box = box | rule
    return box


def _parts(page: Page, paper: Paper, column: tuple[float, float], caption_boxes: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Rectangles that can belong to a figure or table: graphics and small text."""
    not_furniture = lambda r: not paper.is_running(r)
    in_column = lambda r: column[0] - 3 <= (r.x0 + r.x1) / 2 <= column[1] + 3

    rects = list(page.graphics)
    rects += [line.bbox for line in page.lines if line.size < paper.body_size - 0.6]  # labels, cells
    rects += _cells_in_body_size(page, paper)
    return [r for r in rects if not_furniture(r) and in_column(r) and not _inside_any(r, caption_boxes)]


def _cells_in_body_size(page: Page, paper: Paper) -> list[pymupdf.Rect]:
    """Table cells and image labels set in the body font size.

    Such a line is told apart from running text by its row: it is short and has a
    short neighbour on the same row with white space between them ("GbS [3]"
    next to "53.40 70.48 ..."). Text lines of a paragraph are long.
    """
    short = [line for line in page.lines if len(line.text.strip()) < 40]
    cells = []
    for line in short:
        if not paper.is_body(line):
            continue
        for other in short:
            same_row = min(line.bbox.y1, other.bbox.y1) - max(line.bbox.y0, other.bbox.y0) >= 0.6 * min(line.bbox.height, other.bbox.height)
            apart = other.bbox.x0 - line.bbox.x1 >= 6 or line.bbox.x0 - other.bbox.x1 >= 6
            if other is not line and same_row and apart:
                cells.append(line.bbox)
                break
    return cells


def _paragraphs(page: Page, paper: Paper, column: tuple[float, float], caption_boxes: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Lines of running text; a figure never grows across one of these."""
    column_width = column[1] - column[0]
    return [
        line.bbox for line in page.lines
        if paper.is_body(line) and line.bbox.width >= 0.5 * column_width and len(line.text) >= 40
        and _is_prose(line.text)
        and line.bbox.x0 < column[1] and line.bbox.x1 > column[0]  # in this column
        and not _inside_any(line.bbox, caption_boxes)
    ]


def _is_prose(text: str) -> bool:
    """Mostly letters: a row of numbers ("48.76 60.08 60.01 ...") is a table row, not running text."""
    chars = [c for c in text if not c.isspace()]
    return bool(chars) and sum(c.isalpha() for c in chars) >= 0.7 * len(chars)


def _grow(caption_box: pymupdf.Rect, parts: list[pymupdf.Rect], barriers: list[pymupdf.Rect], upward: bool):
    """Collect the parts chained to the caption on one side.

    Returns (region, gap) where gap is the white space between caption and the
    nearest part, or None when nothing is attached on that side.
    """
    edge = caption_box.y0 if upward else caption_box.y1  # the edge of the cluster that keeps moving
    # A part on this side may poke a few points into the caption (an image with a white margin).
    on_this_side = [p for p in parts if ((p.y0 + p.y1) / 2 < edge if upward else (p.y0 + p.y1) / 2 > edge)]
    on_this_side.sort(key=lambda r: -r.y1 if upward else r.y0)  # nearest first

    region, first_gap = None, 0.0
    added = True
    while added:
        added = False
        for part in list(on_this_side):
            gap = max(0.0, (edge - part.y1) if upward else (part.y0 - edge))
            max_gap = CAPTION_GAP if region is None else MAX_GAP  # the first part only has to reach the caption
            if gap > max_gap or _blocked(part, edge, barriers, upward):
                continue
            if region is None:
                region, first_gap = pymupdf.Rect(part), gap
            else:
                region = region | part
            edge = region.y0 if upward else region.y1
            on_this_side.remove(part)
            added = True
    return (region, first_gap) if region is not None else None


def _blocked(part: pymupdf.Rect, edge: float, barriers: list[pymupdf.Rect], upward: bool) -> bool:
    """True if a paragraph of body text lies between the cluster edge and the part."""
    for b in barriers:
        between = (b.y1 > part.y1 and b.y0 < edge) if upward else (b.y1 > edge and b.y0 < part.y0)
        if between:
            return True
    return False


def _add_enclosed_text(region: pymupdf.Rect, page: Page, caption_boxes: list[pymupdf.Rect]) -> pymupdf.Rect:
    """Pull in text that sits on the edge of the region (large labels the size filter missed)."""
    grown = pymupdf.Rect(region.x0 - 6, region.y0 - 6, region.x1 + 6, region.y1 + 6)
    for line in page.lines:
        center = pymupdf.Point((line.bbox.x0 + line.bbox.x1) / 2, (line.bbox.y0 + line.bbox.y1) / 2)
        if grown.contains(center) and not _inside_any(line.bbox, caption_boxes):
            region = region | line.bbox
    return region


def _include_straddlers(region: pymupdf.Rect, parts: list[pymupdf.Rect], column: tuple[float, float], caption_boxes: list[pymupdf.Rect]) -> pymupdf.Rect:
    """Grow the region over parts that cross its edge, so no text or shape is cut in half.

    Repeats until nothing crosses the edge. Parts wider than the column and parts
    touching a caption are never taken.
    """
    max_width = column[1] - column[0] + 10
    growing = True
    while growing:
        growing = False
        for part in parts:
            crosses = part.intersects(region) and not region.contains(part)
            if crosses and part.width <= max_width and not any(part.intersects(c) for c in caption_boxes):
                region = region | part
                growing = True
    return region


def _inside_any(rect: pymupdf.Rect, boxes: list[pymupdf.Rect]) -> bool:
    """True if rect lies (almost) entirely inside one of the boxes, e.g. a caption's own text."""
    area = rect.get_area()
    return any((rect & box).get_area() >= 0.8 * area for box in boxes if area > 0)
