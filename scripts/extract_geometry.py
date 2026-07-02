#!/usr/bin/env python3
"""
extract_geometry.py

Reads a PDF and dumps the vector drawing geometry (rectangles, lines,
text labels, and likely checkbox glyphs) that a flat/non-fillable form
uses to draw its entry lines, cell grids, and checkboxes.

This is step 1 of turning a flat form into a fillable one: you need the
*exact* coordinates the form itself uses, not eyeballed guesses from a
rendered image. Rows are grouped by their top-coordinate so you can see
each visual "row" of the form as one line of output.

Usage:
    python extract_geometry.py <input.pdf> <output.json> [--page N]

Output JSON structure:
{
  "page_height": 841.92,
  "pages": [
    {
      "page_index": 0,
      "rects_by_row": [ [top, [[x0,x1], [x0,x1], ...]], ... ],
      "lines_by_row": [ [top, [[x0,x1], ...]], ... ],
      "words": [ {"text": "...", "x0":.., "top":.., "x1":.., "bottom":..}, ... ],
      "checkbox_glyphs": [ {"text": "...", "x0":.., "top":.., "x1":.., "bottom":..}, ... ]
    },
    ...
  ]
}

Notes:
- Coordinates are in PDF points, TOP-DOWN (top=0 at the top of the page),
  matching pdfplumber's convention. When building AcroForm widgets you must
  convert to PDF's native bottom-up coordinate system:
      y_bottom_up = page_height - top_down_value
- "checkbox_glyphs" flags characters in the Unicode Private Use Area
  (0xE000-0xF8FF), which is how Wingdings/Wingdings2/ZapfDingbats-style
  checkbox/tick glyphs are commonly encoded in generated PDFs (e.g. IND,
  many government forms). Not all forms use this — some draw checkboxes as
  small vector rects instead (already in rects_by_row), and some use plain
  Unicode ballot-box characters like U+2610 (☐), which will just show up
  as ordinary text in "words" — search that list for □/☐/✓/✗ too.
"""
import sys
import json
import argparse
import pdfplumber


def group_by_row(items, top_key="top", tolerance=1.0):
    """Group a list of dicts into rows by rounding their top-coordinate."""
    buckets = {}
    for it in items:
        key = round(it[top_key] / tolerance) * tolerance
        buckets.setdefault(key, []).append(it)
    return sorted(buckets.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_pdf")
    ap.add_argument("output_json")
    ap.add_argument("--page", type=int, default=None,
                     help="Only extract this 0-indexed page (default: all pages)")
    args = ap.parse_args()

    pdf = pdfplumber.open(args.input_pdf)
    page_indices = [args.page] if args.page is not None else range(len(pdf.pages))

    result = {"page_height": float(pdf.pages[0].height), "pages": []}

    for pi in page_indices:
        page = pdf.pages[pi]

        rects = [{"x0": round(r["x0"], 1), "x1": round(r["x1"], 1), "top": round(r["top"], 1)}
                 for r in page.rects]
        lines = [{"x0": round(l["x0"], 1), "x1": round(l["x1"], 1), "top": round(l["top"], 1)}
                 for l in page.lines]
        words = [{"text": w["text"], "x0": round(w["x0"], 1), "top": round(w["top"], 1),
                  "x1": round(w["x1"], 1), "bottom": round(w["bottom"], 1)}
                 for w in page.extract_words()]

        checkbox_glyphs = []
        for ch in page.chars:
            code = ord(ch["text"]) if len(ch["text"]) == 1 else 0
            if 0xE000 <= code <= 0xF8FF:
                checkbox_glyphs.append({
                    "text": ch["text"], "x0": round(ch["x0"], 1), "top": round(ch["top"], 1),
                    "x1": round(ch["x1"], 1), "bottom": round(ch["bottom"], 1)
                })

        rects_by_row = []
        for top, items in group_by_row(rects, tolerance=1.0):
            xs = sorted(set([(it["x0"], it["x1"]) for it in items]))
            rects_by_row.append([top, xs])

        lines_by_row = []
        for top, items in group_by_row(lines, tolerance=1.0):
            xs = sorted(set([(it["x0"], it["x1"]) for it in items]))
            lines_by_row.append([top, xs])

        result["pages"].append({
            "page_index": pi,
            "rects_by_row": rects_by_row,
            "lines_by_row": lines_by_row,
            "words": words,
            "checkbox_glyphs": checkbox_glyphs,
        })

    with open(args.output_json, "w") as f:
        json.dump(result, f, indent=1)

    print(f"Wrote geometry for {len(result['pages'])} page(s) to {args.output_json}")


if __name__ == "__main__":
    main()
