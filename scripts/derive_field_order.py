#!/usr/bin/env python3
"""
derive_field_order.py

Takes a hand-authored field spec (the semantic mapping of labels -> field
types/coordinates that you built while reading the form) and:

  1. Derives the correct tab order purely from geometry — never trust a
     hand-typed order, it's easy to get subtly wrong (we proved this twice).
     Fields are clustered into "rows" by their top-edge (within a tolerance,
     so side-by-side fields on the same visual row still sort left-to-right),
     rows are ordered top-to-bottom, and fields within a row are ordered
     left-to-right.

  2. Assigns each field a zero-padded sequence prefix in its internal PDF
     field name (e.g. "007_sex_male"). This is a defensive measure: some
     PDF viewers, especially on *tagged/accessible* PDFs where newly-added
     widgets aren't represented in the structure tree, fall back to sorting
     fields alphabetically by name rather than respecting annotation order.
     Prefixing guarantees the alphabetical order and the geometric order
     agree, so Tab behaves correctly regardless of which heuristic a given
     viewer uses.

Input field spec (JSON list), one object per field:
    {
      "page": 1,                     # 0-indexed page number
      "kind": "text" | "comb" | "checkbox",
      "name": "vnumber",             # short, human-readable, unique per doc
      "rect": [x0, top, x1, bottom], # TOP-DOWN pdf points (pdfplumber convention)
      "tooltip": "V-number",
      "maxlen": 10                   # required for "comb" fields, omit otherwise
    }

Output: same objects, each with two new keys:
    "order": <int>            global sequence number (1-indexed)
    "prefixed_name": "003_vnumber"

Usage:
    python derive_field_order.py <field_spec_in.json> <field_spec_out.json> [--tolerance 6.0]
"""
import json
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json")
    ap.add_argument("output_json")
    ap.add_argument("--tolerance", type=float, default=6.0,
                     help="Row-clustering tolerance in points (default 6.0)")
    args = ap.parse_args()

    fields = json.load(open(args.input_json))

    by_page = {}
    for f in fields:
        by_page.setdefault(f["page"], []).append(f)

    ordered_all = []
    for page_idx in sorted(by_page.keys()):
        items = by_page[page_idx]
        # sort by top ascending, then left edge ascending
        items_sorted = sorted(items, key=lambda it: (it["rect"][1], it["rect"][0]))
        buckets = []
        for it in items_sorted:
            top = it["rect"][1]
            if buckets and abs(top - buckets[-1]["ref_top"]) <= args.tolerance:
                buckets[-1]["items"].append(it)
            else:
                buckets.append({"ref_top": top, "items": [it]})
        for b in buckets:
            row_items = sorted(b["items"], key=lambda it: it["rect"][0])
            ordered_all.extend(row_items)

    for i, f in enumerate(ordered_all, start=1):
        f["order"] = i
        f["prefixed_name"] = f"{i:03d}_{f['name']}"

    json.dump(ordered_all, open(args.output_json, "w"), indent=1)

    print(f"Ordered {len(ordered_all)} fields across {len(by_page)} page(s).")
    print(f"Wrote {args.output_json}")
    print()
    print("Review this order before building — this is your check/fix step.")
    print("If any field is in a row-cluster it shouldn't be (e.g. a tall")
    print("field accidentally grouped with a neighboring short field),")
    print("adjust --tolerance or fix the input rect and re-run.")
    for f in ordered_all:
        print(f"  {f['order']:3d}  page={f['page']+1}  {f['kind']:8s}  {f['prefixed_name']}")


if __name__ == "__main__":
    main()
