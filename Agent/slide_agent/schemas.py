"""Data passed between stages (stored in session state as dicts)."""

from typing import Literal

from pydantic import BaseModel, Field


class Asset(BaseModel):
    """A figure, table, algorithm or equation cropped from the paper PDF."""

    id: str = Field(description="fig_2, tab_1, alg_1, eq_3, ...")
    kind: Literal["figure", "table", "algorithm", "equation"]
    number: str = Field(description="The number printed in the paper, e.g. '2' or '4a'.")
    page: int = Field(description="1-based page number.")
    bbox: tuple[float, float, float, float] = Field(description="Crop rectangle in PDF points (x0, y0, x1, y1).")
    caption: str = Field(default="", description="Caption; for equations, the text line just above it.")
    image_path: str = Field(description="PNG path relative to the output directory.")
    size_px: tuple[int, int] = Field(description="Image size (width, height) in pixels.")
    in_appendix: bool = False
    mentioned_in: list[str] = Field(
        default_factory=list, description="Section headings whose text refers to this asset."
    )


class ExtractionSettings(BaseModel):
    """The options extract_assets was run with."""

    kinds: list[str]
    include_appendix: bool
    dpi: int


class AssetManifest(BaseModel):
    """Everything extract_assets found in one paper (saved as assets.json)."""

    pdf: str
    settings: ExtractionSettings
    num_pages: int
    appendix_start_page: int | None = None
    assets: list[Asset]
    warnings: list[str] = Field(default_factory=list)


class SlideSpec(BaseModel):
    title: str
    key_message: str = Field(description="One sentence the audience should take away.")
    bullets: list[str] = Field(default_factory=list, description="At most 5.")
    asset_ids: list[str] = Field(default_factory=list, description="Asset.id values placed on this slide.")
    notes: str = Field(default="", description="Speaker notes.")


class Outline(BaseModel):
    slides: list[SlideSpec]
