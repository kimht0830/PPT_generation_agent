"""Tests for the asset extractor.

Two groups:
  * unit tests   - small pure helpers (regexes, id naming); no PDF needed
  * paper tests  - run extract_assets on real papers from ../examples and check the result
"""

import json
from collections import Counter

import pymupdf
import pytest

from slide_agent.config import EXAMPLES_DIR
from slide_agent.tools.asset_extractor import extract_assets
from slide_agent.tools.asset_extractor.captions import CAPTION
from slide_agent.tools.asset_extractor.equations import NUMBER
from slide_agent.tools.asset_extractor.extractor import _unique_id


# --------------------------------------------------------------------------- unit tests

@pytest.mark.parametrize("text, kind, number", [
    ("Figure 2. Overview of our method", "figure", "2"),
    ("Fig. 3: Qualitative results", "fig.", "3"),
    ("Table 1 | Results on ImageNet", "table", "1"),
    ("Algorithm 1: Training loop", "algorithm", "1"),
    ("Figure A3. Extra results", "figure", "A3"),
])
def test_caption_regex_matches(text, kind, number):
    match = CAPTION.match(text)
    assert match is not None
    assert match.group(1).lower() == kind
    assert match.group(2) == number


@pytest.mark.parametrize("text", [
    "Figure 2 shows the overview",  # a sentence that mentions a figure, not a caption
    "As in Table 1, we ...",
    "Tables 1 and 2",
])
def test_caption_regex_rejects_references(text):
    assert CAPTION.match(text) is None


@pytest.mark.parametrize("text, number", [
    ("(3)", "3"),
    ("x = y + z  (12)", "12"),
    ("(4a)", "4a"),
])
def test_equation_number_regex(text, number):
    assert NUMBER.search(text).group(1) == number


def test_equation_number_regex_rejects_plain_text():
    assert NUMBER.search("as shown in (Smith et al., 2023) here") is None


def test_unique_id_resolves_collisions():
    used: set[str] = set()
    assert _unique_id("fig", "1", used, in_appendix=False) == "fig_1"
    assert _unique_id("fig", "1", used, in_appendix=True) == "fig_1_app"
    assert _unique_id("fig", "1", used, in_appendix=False) == "fig_1_dup"
    assert _unique_id("fig", "1", used, in_appendix=True) == "fig_1_2"


# --------------------------------------------------------------------------- paper tests

def _paper(name):
    path = EXAMPLES_DIR / name / "paper.pdf"
    if not path.exists():
        pytest.skip(f"{path} not available")
    return path


@pytest.fixture(scope="module")
def cvpr_manifest(tmp_path_factory):
    out = tmp_path_factory.mktemp("cvpr2023")
    return extract_assets(_paper("CVPR2023_22201_ZYGCbfZ"), out, dpi=100), out


@pytest.fixture(scope="module")
def eccv_manifest(tmp_path_factory):
    out = tmp_path_factory.mktemp("eccv2024")
    return extract_assets(_paper("ECCV2024_1823"), out, dpi=100), out


def _counts(manifest):
    return Counter(a.kind for a in manifest.assets)


def test_cvpr2023_counts(cvpr_manifest):
    manifest, _ = cvpr_manifest
    assert _counts(manifest) == {"figure": 4, "table": 8, "algorithm": 1, "equation": 18}
    assert manifest.warnings == []


def test_eccv2024_counts(eccv_manifest):
    manifest, _ = eccv_manifest
    assert _counts(manifest) == {"figure": 2, "table": 4, "equation": 3}
    assert manifest.warnings == []


@pytest.mark.parametrize("fixture", ["cvpr_manifest", "eccv_manifest"])
def test_outputs_are_consistent(fixture, request):
    manifest, out = request.getfixturevalue(fixture)

    ids = [a.id for a in manifest.assets]
    assert len(ids) == len(set(ids)), "asset ids must be unique"

    for asset in manifest.assets:
        assert (out / asset.image_path).is_file()
        assert asset.size_px[0] > 0 and asset.size_px[1] > 0
        assert 1 <= asset.page <= manifest.num_pages
        x0, y0, x1, y1 = asset.bbox
        assert x1 > x0 and y1 > y0

    saved = json.loads((out / "assets.json").read_text(encoding="utf-8"))
    assert [a["id"] for a in saved["assets"]] == ids


def test_bboxes_stay_inside_their_page(cvpr_manifest):
    manifest, _ = cvpr_manifest
    doc = pymupdf.open(_paper("CVPR2023_22201_ZYGCbfZ"))
    for asset in manifest.assets:
        page_rect = doc[asset.page - 1].rect
        assert pymupdf.Rect(asset.bbox) in page_rect + (-0.2, -0.2, 0.2, 0.2), asset.id


def test_crop_does_not_include_caption(cvpr_manifest):
    manifest, _ = cvpr_manifest
    doc = pymupdf.open(_paper("CVPR2023_22201_ZYGCbfZ"))
    for asset in manifest.assets:
        if asset.kind in ("equation", "algorithm"):  # an algorithm's title sits inside its box
            continue
        text_in_crop = doc[asset.page - 1].get_text("text", clip=pymupdf.Rect(asset.bbox))
        caption_lines = [ln for ln in text_in_crop.splitlines() if CAPTION.match(ln.strip())]
        assert caption_lines == [], asset.id


def test_kinds_filter(tmp_path):
    manifest = extract_assets(_paper("ECCV2024_1823"), tmp_path, kinds=("table",), dpi=72)
    assert set(_counts(manifest)) == {"table"}


def test_settings_are_recorded(tmp_path):
    extract_assets(_paper("ECCV2024_1823"), tmp_path, kinds=("table",), include_appendix=False, dpi=72)
    saved = json.loads((tmp_path / "assets.json").read_text(encoding="utf-8"))
    assert saved["settings"] == {"kinds": ["table"], "include_appendix": False, "dpi": 72}


def test_exclude_appendix(tmp_path):
    manifest = extract_assets(_paper("ICML2024_34150"), tmp_path, include_appendix=False, dpi=72)
    assert manifest.appendix_start_page is not None
    assert not any(a.in_appendix for a in manifest.assets)
