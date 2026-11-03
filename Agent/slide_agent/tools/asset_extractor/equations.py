"""Step 4: find numbered display equations.

A numbered equation ends with its number, right-aligned in the column: "(3)".
We take that number as the anchor and collect the formula pieces on its row
(fractions and sub/superscripts are separate lines in the PDF, so we grow
upward and downward over math lines).
"""

import re
from dataclasses import dataclass

import pymupdf

from .page_content import Line, Page, Paper

NUMBER = re.compile(r"\(\s*(\d{1,3}[a-z]?)\s*\)\s*$")  # "(12)" or "(4a)" at the end of a line
ROW_PAD = 8  # largest vertical gap (pt) between the lines of one formula (its number may sit below it)


@dataclass(eq=False)
class Equation:
    number: str
    page: int  # 1-based
    bbox: pymupdf.Rect
    context: str  # the line of text just above the equation


def find_equations(paper: Paper) -> list[Equation]:
    equations = []
    for page in paper.pages:
        numbered = []  # (line holding the number, regex match)
        for line in page.lines:
            match = NUMBER.search(line.text)
            if match and _is_equation_number(line, match, paper):
                numbered.append((line, match))
        number_lines = [line for line, _ in numbered]
        for line, match in numbered:
            bbox = _equation_rect(line, number_lines, page, paper)
            equations.append(Equation(match.group(1), page.number, bbox, _context(bbox, page, paper)))
    return equations


def _is_equation_number(line: Line, match: re.Match, paper: Paper) -> bool:
    """The number must sit at the right edge of the column, alone or after math.

    This rejects body lines that merely end in "(2023)" or "(see Sec. 2)".
    """
    column = paper.column_at(line.bbox)
    right_aligned = line.bbox.x1 >= column[1] - 4
    alone = line.text.strip() == match.group(0).strip()
    return right_aligned and (alone or line.math_ratio >= 0.2)


def _equation_rect(number_line: Line, number_lines: list[Line], page: Page, paper: Paper) -> pymupdf.Rect:
    """Grow from the number over the lines of its formula.

    Equations stacked in one block (aligned rows, each with its own number) share
    math lines; every line is given to the nearest number only.
    """
    column = paper.column_at(number_line.bbox)
    column_numbers = [n for n in number_lines if paper.column_at(n.bbox) == column]
    candidates = [
        line for line in page.lines
        if line is not number_line and line.bbox.x0 >= column[0] - 3 and line.bbox.x1 <= column[1] + 3
        and min(column_numbers, key=lambda n: abs(_center_y(n) - _center_y(line))) is number_line
    ]
    rect = pymupdf.Rect(number_line.bbox)
    added = True
    while added:
        added = False
        for line in list(candidates):
            if _belongs(line, rect, column, paper):
                rect = rect | line.bbox
                candidates.remove(line)
                added = True
    return rect


def _center_y(line: Line) -> float:
    return (line.bbox.y0 + line.bbox.y1) / 2


def _belongs(line: Line, rect: pymupdf.Rect, column: tuple[float, float], paper: Paper) -> bool:
    """Does this line belong to the formula whose area is rect so far?"""
    is_math = (
        line.math_ratio >= 0.3
        or line.size < paper.body_size - 1.5  # sub/superscripts
        or (line.math_ratio > 0 and line.bbox.width < 0.5 * (column[1] - column[0]))  # short line with some math, e.g. a denominator
    )
    if is_math:
        return line.bbox.y1 >= rect.y0 - ROW_PAD and line.bbox.y0 <= rect.y1 + ROW_PAD
    # ordinary text counts only when it is on the same row ("if", "otherwise", "arg max")
    overlap = min(line.bbox.y1, rect.y1) - max(line.bbox.y0, rect.y0)
    return overlap >= 0.5 * line.bbox.height


def _context(rect: pymupdf.Rect, page: Page, paper: Paper) -> str:
    column = paper.column_at(rect)
    above = [
        line for line in page.lines
        if paper.is_body(line) and line.math_ratio < 0.3 and line.bbox.y1 <= rect.y0 + 1
        and line.bbox.x0 < column[1] and line.bbox.x1 > column[0]
    ]
    nearest = max(above, key=lambda line: line.bbox.y1, default=None)
    return nearest.text[-120:] if nearest else ""
