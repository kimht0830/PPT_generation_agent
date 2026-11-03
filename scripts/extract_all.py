"""Run the asset extractor on every paper in examples/ and write one summary.

Usage (from the Agent folder, with its venv):
    python ../scripts/extract_all.py [--dpi 300] [--out DIR]

Each paper goes to <out>/<paper folder name>/ ; <out>/summary.json lists the
counts, warnings and errors per paper (handy for comparing runs of the extractor).
"""

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "Agent"
sys.path.insert(0, str(AGENT_DIR))

from slide_agent.config import EXAMPLES_DIR, OUTPUT_DIR  # noqa: E402
from slide_agent.tools.asset_extractor import extract_assets  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_all_examples")
    args = parser.parse_args()

    papers = sorted(p for p in EXAMPLES_DIR.iterdir() if (p / "paper.pdf").is_file())
    print(f"{len(papers)} papers -> {args.out}", flush=True)

    summary = {}
    for i, folder in enumerate(papers, 1):
        start = time.time()
        try:
            manifest = extract_assets(folder / "paper.pdf", args.out / folder.name, dpi=args.dpi)
            counts = {k: sum(a.kind == k for a in manifest.assets) for k in ("figure", "table", "algorithm", "equation")}
            summary[folder.name] = {"counts": counts, "warnings": manifest.warnings}
            note = f"{sum(counts.values())} assets, {len(manifest.warnings)} warnings"
        except Exception:
            summary[folder.name] = {"error": traceback.format_exc(limit=3)}
            note = "ERROR"
        print(f"[{i}/{len(papers)}] {folder.name}: {note} ({time.time() - start:.0f}s)", flush=True)

    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    errors = [name for name, s in summary.items() if "error" in s]
    print(f"done. {len(papers) - len(errors)} ok, {len(errors)} errors", flush=True)


if __name__ == "__main__":
    main()
