#!/usr/bin/env python3
"""
diagnose_overlapping_fields.py

Finds and reports fields in the generated specs that directly overlap
significant static text on the PDF pages. This indicates that static text (labels,
questions, headers) is being covered by fillable text fields.
"""
import sys
import os
import json
import pdfplumber

def main():
    if len(sys.argv) < 3:
        print("Usage: python diagnose_overlapping_fields.py <input.pdf> <ordered_field_spec.json>")
        sys.exit(1)

    input_pdf = sys.argv[1]
    spec_json = sys.argv[2]

    pdf = pdfplumber.open(input_pdf)
    fields = json.load(open(spec_json))

    print(f"=== Diagnosing overlaps for {os.path.basename(input_pdf)} ===")
    print(f"Total fields in spec: {len(fields)}")

    overlaps_count = 0
    for f in fields:
        page_idx = f["page"]
        if page_idx >= len(pdf.pages):
            continue
        page = pdf.pages[page_idx]
        words = page.extract_words()

        fx0, ftop, fx1, fbottom = f["rect"]

        # Find words that are completely inside or substantially overlap the field rect
        overlapping_words = []
        for w in words:
            # Check for bounding box intersection
            overlap_x = max(0, min(fx1, w["x1"]) - max(fx0, w["x0"]))
            overlap_y = max(0, min(fbottom, w["bottom"]) - max(ftop, w["top"]))
            
            if overlap_x > 0 and overlap_y > 0:
                word_w = w["x1"] - w["x0"]
                word_h = w["bottom"] - w["top"]
                word_area = word_w * word_h
                overlap_area = overlap_x * overlap_y
                # If overlap area is more than 30% of the word area, consider it overlapping
                if overlap_area / word_area > 0.3:
                    overlapping_words.append(w["text"])

        if overlapping_words:
            sentence = " ".join(overlapping_words)
            # Only print if overlapping words contain actual alphabet characters and are substantial
            if len(sentence) > 3 and any(c.isalpha() for c in sentence):
                overlaps_count += 1
                if overlaps_count <= 20:
                    field_label = f.get("name", f.get("prefixed_name", "<unnamed>"))
                    print(f"Field {field_label} ({f['kind']}) on page {page_idx+1}:")
                    print(f"  Rect: [{fx0:.1f}, {ftop:.1f}, {fx1:.1f}, {fbottom:.1f}]")
                    print(f"  Overlaps static text: \"{sentence}\"")
                    print()

    print(f"Total fields overlapping static text: {overlaps_count} / {len(fields)}")

if __name__ == "__main__":
    main()
