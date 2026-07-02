#!/usr/bin/env python3
"""
check_fillable_fields.py

Step 0 of the workflow: confirm the PDF actually needs this treatment.
If it already has a real AcroForm, just fill that instead (any standard
PDF library can do that) — this toolkit is specifically for building
fields from scratch on a flat PDF, not for filling existing ones.

Usage:
    python check_fillable_fields.py <input.pdf>
"""
import sys
from pypdf import PdfReader


def main():
    if len(sys.argv) != 2:
        print("Usage: python check_fillable_fields.py <input.pdf>")
        sys.exit(1)

    reader = PdfReader(sys.argv[1])
    fields = reader.get_fields()

    if fields:
        print(f"This PDF already has {len(fields)} fillable form field(s).")
        print("You don't need this toolkit — fill the existing fields directly")
        print("(e.g. pypdf's update_page_form_field_values, or any PDF filler).")
    else:
        print("This PDF has no fillable form fields.")
        print("Proceed with this toolkit: extract_geometry.py -> build a field")
        print("spec -> derive_field_order.py -> build_form.py -> verify_fill.py")
        print("(see SKILL.md).")


if __name__ == "__main__":
    main()
