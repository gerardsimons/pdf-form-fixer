#!/usr/bin/env python3
"""
render_pages.py

Renders each page of a PDF to a PNG so you can look at the form normally
(labels, layout, checkboxes) side by side with geometry.json while writing
the field spec by hand. Self-contained — uses pdftoppm (poppler-utils) if
available, falling back to pdf2image.

Usage:
    python render_pages.py <input.pdf> <output_dir> [--dpi 120]
"""
import sys
import os
import argparse
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_pdf")
    ap.add_argument("output_dir")
    ap.add_argument("--dpi", type=int, default=120)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(args.dpi), args.input_pdf,
             os.path.join(args.output_dir, "page")],
            check=True
        )
        print(f"Rendered pages to {args.output_dir}/page-*.png")
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    try:
        from pdf2image import convert_from_path
        images = convert_from_path(args.input_pdf, dpi=args.dpi)
        for i, img in enumerate(images, start=1):
            img.save(os.path.join(args.output_dir, f"page_{i}.png"))
        print(f"Rendered pages to {args.output_dir}/page_*.png")
    except ImportError:
        print("Could not render PNGs: neither pdftoppm nor pdf2image is available.")
        print("Install poppler-utils (provides pdftoppm) or `pip install pdf2image`.")
        sys.exit(1)


if __name__ == "__main__":
    main()
