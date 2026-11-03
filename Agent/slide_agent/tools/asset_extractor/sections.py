"""Step 5: paper structure - section headings, where the appendix starts, and
which sections mention which figure / table / equation ("Fig. 3", "Eq. (2)")."""

import re
from collections import defaultdict
from dataclasses import dataclass

import pymupdf

from .page_content import Line, Paper

# "3 Method", "3.1. Annealing Scheme", "A. Extra Results"
HEADING = re.compile(r"^(\d+(\.\d+)*\.?|[A-Z](\.\d+)*\.?)\s+[A-Za-z]")
SPECIAL_HEADING = re.compile(r"^(Abstract|References|Bibliography|Appendix|Supplementary|Supplemental)\b", re.I)
REFERENCES = re.compile(r"^(References|Bibliography)$", re.I)
APPENDIX = re.compile(r"^(Appendix|Supplementary|Supplemental)\b", re.I)
APPENDIX_LETTER = re.compile(r"^[A-Z](\.\d+)*\.?\s+[A-Za-z]")  # "A. Details" (capital letter, case-sensitive)

_NUM = r"[A-Z]?\d+[a-z]?"
_MORE = rf"((?:\s*(?:,|and|&|or)\s*\(?{_NUM}\)?)*)"  # "... and 3", ", 4"
REFERENCE_PATTERNS = {
    "figure": re.compile(rf"\b(?:Figs?\.|Figures?)\s*\(?({_NUM})\)?{_MORE}"),
    "table": re.compile(rf"\bTables?\s*\(?({_NUM})\)?{_MORE}"),
    "algorithm": re.compile(rf"\bAlgorithms?\s*\(?({_NUM})\)?{_MORE}"),
    "equation": re.compile(rf"\b(?:Eqs?\.|Eqns?\.|Equations?)\s*\(?({_NUM})\)?{_MORE}"),
}


@dataclass
class Heading:
    text: str
    page: int
    y: float


def is_heading(line: Line, paper: Paper) -> bool:
    if line.size < paper.body_size - 0.3 or not (line.bold or line.size >= paper.body_size + 2):
        return False
    return bool(HEADING.match(line.text) or SPECIAL_HEADING.match(line.text))


def find_headings(paper: Paper) -> list[Heading]:
    return [
        Heading(line.text, page.number, line.bbox.y0)
        for page in paper.pages for line in page.lines if is_heading(line, paper)
    ]


def find_appendix_start(headings: list[Heading]) -> tuple[int, float] | None:
    """(page, y) of the first appendix heading after the References, if any."""
    references = next((h for h in headings if REFERENCES.match(h.text)), None)
    if references is None:
        return None
    for h in headings:
        if (h.page, h.y) > (references.page, references.y) and (APPENDIX.match(h.text) or APPENDIX_LETTER.match(h.text)):
            return (h.page, h.y)
    return None


def find_mentions(paper: Paper, caption_boxes: dict[int, list[pymupdf.Rect]]) -> dict[tuple[str, str], list[str]]:
    """{(kind, number): [headings of the sections that refer to it]}."""
    mentions: dict[tuple[str, str], list[str]] = defaultdict(list)
    section = "Front matter"
    for page in paper.pages:
        boxes = caption_boxes.get(page.number, [])
        for i, line in enumerate(page.lines):
            if is_heading(line, paper):
                section = line.text
                continue
            if not paper.is_body(line) or any(_mostly_inside(line.bbox, box) for box in boxes):
                continue
            # a reference can wrap onto the next line ("Fig." / "3"), so look a few characters ahead
            next_text = page.lines[i + 1].text[:8] if i + 1 < len(page.lines) else ""
            text = f"{line.text} {next_text}"
            for kind, pattern in REFERENCE_PATTERNS.items():
                for match in pattern.finditer(text):
                    if match.start() >= len(line.text):
                        continue
                    for number in re.findall(_NUM, match.group(1) + match.group(2)):
                        key = (kind, _base_number(kind, number))
                        if section not in mentions[key]:
                            mentions[key].append(section)
    return mentions


def _base_number(kind: str, number: str) -> str:
    """Figure 3a is a panel of Figure 3; equations keep their letter ((4a) is its own equation)."""
    return number if kind == "equation" else re.sub(r"[a-z]$", "", number)


def _mostly_inside(rect: pymupdf.Rect, box: pymupdf.Rect) -> bool:
    return rect.get_area() > 0 and (rect & box).get_area() >= 0.8 * rect.get_area()
