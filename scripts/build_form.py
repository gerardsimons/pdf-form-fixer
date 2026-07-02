#!/usr/bin/env python3
"""
build_form.py

Generic engine that takes a flat/non-fillable PDF plus an ordered field
spec (the output of derive_field_order.py) and produces a real fillable
AcroForm PDF.

Field kinds supported:
  - "text"      A normal single-line text field.
  - "comb"      A "comb" text field: ONE field that auto-spaces typed
                characters into equal-width cells across its Rect. Use this
                for any printed row of individual tick-boxes meant to hold
                one character each (V-numbers, dates split into DD MM YYYY,
                postcodes, reference numbers, etc). Do NOT create one field
                per cell — a single comb field gives the same visual result
                with far better UX (one click, type the whole value).
                Requires "maxlen" = number of cells.
  - "checkbox"  A /Btn field with generated On/Off appearance streams (a
                simple box + X mark). Real appearance streams are required —
                relying on /NeedAppearances alone leaves many viewers
                (especially non-Acrobat ones) rendering nothing.

What this script does NOT do (by design):
  - It never creates a field over a "Signature of ..." line. A typed name
    is not a signature; leave those lines blank for physical/digital
    signing after the form is filled.
  - It doesn't guess field coordinates — it trusts the "rect" values in the
    field spec exactly (TOP-DOWN pdfplumber convention: [x0, top, x1, bottom]),
    converting to PDF bottom-up coordinates internally.

Usage:
    python build_form.py <source.pdf> <ordered_field_spec.json> <output.pdf>

Also writes <output_dir>/name_map.json mapping each field's short "name"
to its actual "prefixed_name" in the PDF, so you can fill it programmatically
without typing the numeric prefixes everywhere.
"""
import sys
import json
import os
import argparse
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    NameObject, TextStringObject, DictionaryObject, ArrayObject,
    NumberObject, BooleanObject, DecodedStreamObject, FloatObject
)

COMB_FLAG = 1 << 24  # PDF spec: text field flag bit 25 = Comb


def make_checkbox_ap(rect_w, rect_h, checked):
    stream = DecodedStreamObject()
    if checked:
        content = (
            f"q 1 1 {rect_w-2:.2f} {rect_h-2:.2f} re S "
            f"0 0 0 RG 1.2 w "
            f"{rect_w*0.2:.2f} {rect_h*0.2:.2f} m {rect_w*0.8:.2f} {rect_h*0.8:.2f} l S "
            f"{rect_w*0.2:.2f} {rect_h*0.8:.2f} m {rect_w*0.8:.2f} {rect_h*0.2:.2f} l S Q"
        )
    else:
        content = f"q 1 1 {rect_w-2:.2f} {rect_h-2:.2f} re S Q"
    stream.set_data(content.encode("latin-1"))
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    stream[NameObject("/FormType")] = NumberObject(1)
    stream[NameObject("/BBox")] = ArrayObject(
        [FloatObject(0), FloatObject(0), FloatObject(rect_w), FloatObject(rect_h)]
    )
    stream[NameObject("/Resources")] = DictionaryObject()
    return stream


def to_pdf_rect(x0, top, x1, bottom, page_height):
    """Convert TOP-DOWN [x0, top, x1, bottom] to PDF native bottom-up rect."""
    return [x0, page_height - bottom, x1, page_height - top]


def build(source_pdf, field_spec_path, output_pdf,
          highlight_bg=(0.93, 0.96, 1.0), border_color=(0.55, 0.65, 0.85)):
    fields = json.load(open(field_spec_path))
    fields = sorted(fields, key=lambda f: f["order"])  # enforce geometric order

    reader = PdfReader(source_pdf)
    writer = PdfWriter()
    writer.append(reader)
    page_height = float(reader.pages[0].mediabox.height)

    acroform_fields = ArrayObject()
    touched_pages = set()

    for f in fields:
        page_idx = f["page"]
        kind = f["kind"]
        name = f["prefixed_name"]
        tooltip = f.get("tooltip", f["name"])
        x0, top, x1, bottom = f["rect"]
        rect = to_pdf_rect(x0, top, x1, bottom, page_height)
        page = writer.pages[page_idx]
        touched_pages.add(page_idx)

        if kind in ("text", "comb"):
            da = "/Helv 9 Tf 1 0 0 rg" if kind == "text" else "/Helv 10 Tf 1 0 0 rg"
            field_dict = DictionaryObject()
            field_dict.update({
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/TU"): TextStringObject(tooltip),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/F"): NumberObject(4),  # Print flag
                NameObject("/DA"): TextStringObject(da),
                NameObject("/MK"): DictionaryObject({
                    NameObject("/BC"): ArrayObject([FloatObject(c) for c in border_color]),
                    NameObject("/BG"): ArrayObject([FloatObject(c) for c in highlight_bg]),
                }),
                NameObject("/BS"): DictionaryObject({
                    NameObject("/W"): FloatObject(0.75),
                    NameObject("/S"): NameObject("/S"),
                }),
            })
            if kind == "comb":
                maxlen = f.get("maxlen")
                if not maxlen:
                    raise ValueError(f"Field '{f['name']}' is kind=comb but has no maxlen")
                field_dict[NameObject("/Ff")] = NumberObject(COMB_FLAG)
                field_dict[NameObject("/MaxLen")] = NumberObject(int(maxlen))
            elif f.get("multiline"):
                field_dict[NameObject("/Ff")] = NumberObject(1 << 12)  # Multiline flag (bit 13)
            else:
                field_dict[NameObject("/Ff")] = NumberObject(0)

        elif kind == "checkbox":
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            ap_off = writer._add_object(make_checkbox_ap(w, h, False))
            ap_on = writer._add_object(make_checkbox_ap(w, h, True))
            ap_dict = DictionaryObject()
            n_dict = DictionaryObject()
            n_dict[NameObject("/Off")] = ap_off
            n_dict[NameObject("/Yes")] = ap_on
            ap_dict[NameObject("/N")] = n_dict

            field_dict = DictionaryObject()
            field_dict.update({
                NameObject("/FT"): NameObject("/Btn"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/TU"): TextStringObject(tooltip),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/F"): NumberObject(4),
                NameObject("/AS"): NameObject("/Off"),
                NameObject("/AP"): ap_dict,
                NameObject("/MK"): DictionaryObject({
                    NameObject("/BC"): ArrayObject([FloatObject(0.3), FloatObject(0.3), FloatObject(0.3)]),
                }),
            })
        else:
            raise ValueError(f"Unknown field kind: {kind}")

        field_ref = writer._add_object(field_dict)
        if "/Annots" in page:
            page["/Annots"].append(field_ref)
        else:
            page[NameObject("/Annots")] = ArrayObject([field_ref])
        field_dict[NameObject("/P")] = writer.get_object(page.indirect_reference)
        acroform_fields.append(field_ref)

    # Force widget-order tab navigation on every page that received fields.
    # (Important on tagged/accessible PDFs, which may otherwise prefer
    # structure-tree order for Tab navigation.)
    for page_idx in touched_pages:
        writer.pages[page_idx][NameObject("/Tabs")] = NameObject("/W")

    acroform = DictionaryObject()
    acroform[NameObject("/Fields")] = acroform_fields
    acroform[NameObject("/NeedAppearances")] = BooleanObject(True)
    acroform[NameObject("/DA")] = TextStringObject("/Helv 9 Tf 1 0 0 rg")

    dr = DictionaryObject()
    font_dict = DictionaryObject()
    helv = DictionaryObject()
    helv[NameObject("/Type")] = NameObject("/Font")
    helv[NameObject("/Subtype")] = NameObject("/Type1")
    helv[NameObject("/BaseFont")] = NameObject("/Helvetica")
    helv[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
    font_dict[NameObject("/Helv")] = writer._add_object(helv)
    dr[NameObject("/Font")] = font_dict
    acroform[NameObject("/DR")] = dr

    writer._root_object[NameObject("/AcroForm")] = acroform

    with open(output_pdf, "wb") as fh:
        writer.write(fh)

    name_map = {f["name"]: f["prefixed_name"] for f in fields}
    name_map_path = os.path.join(os.path.dirname(os.path.abspath(output_pdf)), "name_map.json")
    json.dump(name_map, open(name_map_path, "w"), indent=1)

    print(f"Wrote {output_pdf} with {len(fields)} fields across {len(touched_pages)} page(s).")
    print(f"Wrote {name_map_path} (logical name -> PDF field name)")


def main():
    # Set high recursion limit for parsing highly complex/tagged PDFs in pypdf
    import sys
    sys.setrecursionlimit(100000)

    ap = argparse.ArgumentParser()
    ap.add_argument("source_pdf")
    ap.add_argument("field_spec_json", help="Output of derive_field_order.py")
    ap.add_argument("output_pdf")
    args = ap.parse_args()
    build(args.source_pdf, args.field_spec_json, args.output_pdf)


if __name__ == "__main__":
    main()
