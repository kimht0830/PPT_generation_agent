"""Command line:  python -m slide_agent.tools.asset_extractor paper.pdf [--out DIR] [--sheet]"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .extractor import ALL_KINDS, extract_assets
from .preview import make_contact_sheets


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop figures, tables, algorithms and equations from a paper PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, help="output folder (default: outputs/<timestamp>_<pdf name>)")
    parser.add_argument("--kinds", nargs="+", choices=ALL_KINDS, default=list(ALL_KINDS))
    parser.add_argument("--no-appendix", action="store_true", help="skip assets found in the appendix")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--sheet", action="store_true", help="also write preview_N.jpg contact sheets")
    args = parser.parse_args()

    out_dir = args.out or Path("outputs") / f"{datetime.now():%Y%m%d-%H%M%S}_{args.pdf.stem}"
    manifest = extract_assets(args.pdf, out_dir, tuple(args.kinds), not args.no_appendix, args.dpi)

    counts = {kind: sum(a.kind == kind for a in manifest.assets) for kind in ALL_KINDS}
    print(f"{manifest.pdf}: {len(manifest.assets)} assets {counts} -> {out_dir}")
    for warning in manifest.warnings:
        print(f"  warning: {warning}", file=sys.stderr)
    if args.sheet:
        for path in make_contact_sheets(manifest, out_dir):
            print(f"  preview: {path}")


if __name__ == "__main__":
    main()
