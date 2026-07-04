#!/usr/bin/env python3
"""
verify_fill.py

Fills a built fillable PDF with sample data and renders every page to a PNG
so the result can be visually inspected. This step is MANDATORY, not
optional — coordinate math is easy to get subtly wrong (off-by-one-cell
errors, wrong row, etc.), and the only reliable way to catch that is to
actually look at a rendered, filled page next to the original.

Usage:
    python verify_fill.py <fillable.pdf> <name_map.json> <sample_data.json> <output_dir>

sample_data.json: {"logical_name": "value", ...} using the SHORT field
names from your field spec (not the numeric-prefixed PDF names — this
script does that lookup for you via name_map.json).

For checkbox fields, use the value "/Yes" to check them.
"""
import sys
import os
import json
import argparse
import subprocess
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject


def main():
    # Set high recursion limit for parsing highly complex/tagged PDFs in pypdf
    import sys
    sys.setrecursionlimit(100000)

    ap = argparse.ArgumentParser()
    ap.add_argument("fillable_pdf")
    ap.add_argument("name_map_json")
    ap.add_argument("sample_data_json")
    ap.add_argument("output_dir")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    name_map = json.load(open(args.name_map_json))
    sample_data = json.load(open(args.sample_data_json))

    missing = [k for k in sample_data if k not in name_map]
    if missing:
        print(f"WARNING: these sample_data keys are not in name_map and will be ignored: {missing}")

    mapped_data = {name_map[k]: v for k, v in sample_data.items() if k in name_map}

    reader = PdfReader(args.fillable_pdf)
    writer = PdfWriter()
    writer.append(reader)

    # The shipped PDF's fields use black text (see build_form.py) - but for
    # this debug preview specifically, override to red so misaligned text is
    # immediately obvious against the printed form underneath. This only
    # touches _filled_preview.pdf, never the actual output.pdf deliverable.
    root = writer._root_object
    if "/AcroForm" in root:
        acroform = root["/AcroForm"]
        if "/DA" in acroform:
            acroform[NameObject("/DA")] = TextStringObject("/Helv 9 Tf 1 0 0 rg")
        for field in acroform.get("/Fields", []):
            field_obj = field.get_object()
            if "/DA" in field_obj:
                da = field_obj["/DA"]
                field_obj[NameObject("/DA")] = TextStringObject(da.replace("0 g", "1 0 0 rg"))

    for page in writer.pages:
        writer.update_page_form_field_values(page, mapped_data)

    filled_path = os.path.join(args.output_dir, "_filled_preview.pdf")
    with open(filled_path, "wb") as f:
        writer.write(f)

    # Render pages to PNG for visual review. Uses pdftoppm (poppler-utils)
    # if available, falling back to pdf2image.
    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", "120", filled_path,
             os.path.join(args.output_dir, "page")],
            check=True
        )
        print(f"Rendered pages to {args.output_dir}/page-*.png")
    except (FileNotFoundError, subprocess.CalledProcessError):
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(filled_path, dpi=120)
            for i, img in enumerate(images, start=1):
                out_path = os.path.join(args.output_dir, f"page_{i}.png")
                img.save(out_path)
            print(f"Rendered pages to {args.output_dir}/page_*.png")
        except ImportError:
            print("Could not render PNGs (no pdftoppm or pdf2image available).")
            print(f"Filled PDF is still available at {filled_path}")

    print()
    print("Now VIEW the rendered pages and check, per field:")
    print("  - Does the value sit inside its printed line/box, not overlapping text?")
    print("  - For comb fields (dates, numbers): does each character land in its own cell?")
    print("  - Are checkboxes showing a visible mark when checked?")
    print("  - Tab through the actual PDF in a viewer: does focus follow reading order?")


if __name__ == "__main__":
    main()
