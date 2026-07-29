"""Assemble the Specimen demo GIF from captured frames (called by capture-specimen.spec.ts).

Per-frame durations matter here: the morph frames need to run fast enough to read as motion while
each settled state has to hold long enough for a reader to price the row. A single frame rate
cannot do both, so the capture writes an explicit duration per frame and this script honours it.

Palette: the page is a warm near-black with two script colours and one accent, so 64 colours is
ample and keeps the asset small enough for a README. Frames are quantised against a shared palette
built from the first frame — per-frame palettes make the dark ground shimmer between frames.

Usage: python3 assemble_gif.py <frames.json> <out.gif>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

COLORS = 64


def main() -> None:
    spec_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not spec:
        raise SystemExit("no frames captured")

    frames = [Image.open(entry["file"]).convert("RGB") for entry in spec]
    palette = frames[0].quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT)
    quantised = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]

    quantised[0].save(
        out_path,
        save_all=True,
        append_images=quantised[1:],
        duration=[entry["duration"] for entry in spec],
        loop=0,
        optimize=True,
        disposal=1,
    )
    size_kb = out_path.stat().st_size / 1024
    print(f"{out_path}: {len(quantised)} frames, {frames[0].size[0]}x{frames[0].size[1]}, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
