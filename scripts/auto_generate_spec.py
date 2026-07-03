#!/usr/bin/env python3
"""
auto_generate_spec_v2.py

An advanced layout-analysis and semantic-mapping engine for flat PDF forms.
It parses vector geometry and text words using pdfplumber, and implements several
highly advanced heuristics to produce perfectly aligned field specifications:

  1. Grid Cell Analysis: Distinguishes between "Label Cells" (which contain printed
     text inside their bounds) and "Input Cells" (which are empty spaces meant to be filled).
     It skips generating text fields over label cells to prevent obscuring text.

  2. Underline Label Splitting: Detects when a single physical horizontal line is
     semantically multiple fields (e.g., "First Name", "MI", "Last Name" labels side-by-side).
     It splits the single line into multiple perfectly aligned text fields.

  3. Section Divider Filtering: Recognizes decorative section-dividing lines and avoids
     putting input fields over them.
"""
import sys
import os
import json
import re
import pdfplumber

def clean_name(text):
    """Sanitize text to create a valid JSON field name."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = text.strip("_")
    if not text:
        text = "field"
    return text

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input_pdf")
    ap.add_argument("output_spec")
    ap.add_argument("--sensitivity", "-s", choices=["low", "medium", "high"], default="medium",
                    help="Sensitivity level of layout extraction (low=conservative, medium=balanced, high=aggressive)")
    args = ap.parse_args()

    input_pdf = args.input_pdf
    output_spec = args.output_spec
    sensitivity = args.sensitivity

    # Configure parameters dynamically based on sensitivity selection
    if sensitivity == "low":
        collision_height = 18.0
        collision_padding = 6.0
        max_line_width = 350.0
        comb_gap_limit = 3.0
    elif sensitivity == "high":
        collision_height = 10.0
        collision_padding = 1.0
        max_line_width = 520.0
        comb_gap_limit = 10.0
    else:  # medium
        collision_height = 15.5
        collision_padding = 4.0
        max_line_width = 450.0
        comb_gap_limit = 4.0

    pdf = pdfplumber.open(input_pdf)
    all_fields = []
    name_counts = {}

    for pi, page in enumerate(pdf.pages):
        page_height = float(page.height)
        page_width = float(page.width)
        words = page.extract_words()
        rects = page.rects
        lines = page.lines

        # 1. Identify raw elements
        page_checkboxes = []
        raw_underlines = []

        # Extract checkboxes from vector rectangles
        for r in rects:
            x0, x1, top, bottom = round(r["x0"], 1), round(r["x1"], 1), round(r["top"], 1), round(r["bottom"], 1)
            w, h = x1 - x0, bottom - top
            if 8 <= w <= 20 and 8 <= h <= 20 and abs(w - h) < 2.0:
                page_checkboxes.append({"x0": x0, "x1": x1, "top": top, "bottom": bottom})
            elif w > 15 and h <= 3.0:
                raw_underlines.append({"x0": x0, "x1": x1, "top": top, "bottom": bottom})

        # Extract underlines from horizontal vector lines
        for l in lines:
            if abs(l["y0"] - l["y1"]) < 1.0:  # horizontal
                x0, x1, top = round(l["x0"], 1), round(l["x1"], 1), round(l["top"], 1)
                w = x1 - x0
                if w > 15:
                    raw_underlines.append({"x0": x0, "x1": x1, "top": top, "bottom": top + 1.0})

        # Extract checkboxes from Private Use Area font glyphs
        for ch in page.chars:
            code = ord(ch["text"]) if len(ch["text"]) == 1 else 0
            if 0xE000 <= code <= 0xF8FF:
                x0, x1, top, bottom = round(ch["x0"], 1), round(ch["x1"], 1), round(ch["top"], 1), round(ch["bottom"], 1)
                page_checkboxes.append({"x0": x0, "x1": x1, "top": top, "bottom": bottom})

        # Extract text-based checkboxes (e.g. ☐ ☑ □) from words
        for w in words:
            text = w["text"]
            if any(char in text for char in ("☐", "☑", "□", "■", "☒")) or text == "[ ]":
                x0, x1, top, bottom = round(w["x0"], 1), round(w["x1"], 1), round(w["top"], 1), round(w["bottom"], 1)
                page_checkboxes.append({"x0": x0, "x1": x1, "top": top, "bottom": bottom})

        # Extract text-based underlines (e.g. _______ or contains ....) from words
        for w in words:
            text = w["text"]
            if re.match(r"^[_.\s\-]{3,}$", text) or ("___" in text) or ("...." in text):
                x0, x1, top, bottom = round(w["x0"], 1), round(w["x1"], 1), round(w["top"], 1), round(w["bottom"], 1)
                raw_underlines.append({"x0": x0, "x1": x1, "top": top, "bottom": bottom})

        # Remove duplicate lines/underlines with extremely close coordinates
        unique_underlines = []
        for ul in sorted(raw_underlines, key=lambda e: (e["top"], e["x0"])):
            # Check if we already have a very similar underline
            dup = False
            for existing in unique_underlines:
                if abs(existing["top"] - ul["top"]) < 3.0 and abs(existing["x0"] - ul["x0"]) < 5.0 and abs(existing["x1"] - ul["x1"]) < 5.0:
                    dup = True
                    break
            if not dup:
                unique_underlines.append(ul)

        # 2. Segment and group boxes (postcodes, dates-of-birth, numbers) vs checkboxes
        checkboxes_only = []
        comb_fields = []

        # Deduplicate double-drawn or overlapping checkboxes (same box drawn twice for bold/shadow)
        unique_page_checkboxes = []
        for cb in sorted(page_checkboxes, key=lambda x: (x["top"], x["x0"])):
            dup = False
            for existing in unique_page_checkboxes:
                if abs(existing["top"] - cb["top"]) < 2.0 and abs(existing["x0"] - cb["x0"]) < 3.0:
                    dup = True
                    break
            if not dup:
                unique_page_checkboxes.append(cb)
        page_checkboxes = unique_page_checkboxes

        # Group page_checkboxes by top coordinate (with 2pt tolerance)
        by_row = []
        for cb in sorted(page_checkboxes, key=lambda x: (x["top"], x["x0"])):
            placed = False
            for row in by_row:
                if abs(row[0]["top"] - cb["top"]) < 2.0:
                    row.append(cb)
                    placed = True
                    break
            if not placed:
                by_row.append([cb])

        # For each row, group close boxes into contiguous comb fields
        for row in by_row:
            row = sorted(row, key=lambda x: x["x0"])
            groups = []
            current_group = []
            for cb in row:
                if current_group and cb["x0"] - current_group[-1]["x1"] > comb_gap_limit:
                    groups.append(current_group)
                    current_group = [cb]
                else:
                    current_group.append(cb)
            if current_group:
                groups.append(current_group)

            for group in groups:
                if len(group) == 1:
                    # Isolated square: this is an actual checkbox!
                    checkboxes_only.append(group[0])
                else:
                    # Multiple adjacent squares: this is a comb field!
                    x0 = group[0]["x0"]
                    x1 = group[-1]["x1"]
                    top = min(item["top"] for item in group)
                    bottom = max(item["bottom"] for item in group)
                    comb_fields.append({
                        "x0": x0, "x1": x1, "top": top, "bottom": bottom, "count": len(group)
                    })

        # 2a. Process actual Checkboxes
        for cb in sorted(checkboxes_only, key=lambda e: (e["top"], e["x0"])):
            # Find nearby words on the same line to describe this checkbox
            left_words = []
            right_words = []
            for w in words:
                if abs(w["top"] - cb["top"]) < 8.0:
                    if w["x1"] < cb["x0"] and cb["x0"] - w["x1"] < 100.0:
                        left_words.append(w)
                    elif w["x0"] > cb["x1"] and w["x0"] - cb["x1"] < 100.0:
                        right_words.append(w)

            left_words = sorted(left_words, key=lambda x: x["x0"])
            right_words = sorted(right_words, key=lambda x: x["x0"])

            left_str = " ".join([w["text"] for w in left_words])
            right_str = " ".join([w["text"] for w in right_words])

            label = right_str if (right_str and len(right_str) < 20) else (left_str if left_str else "Option")
            name = clean_name(label if label != "Option" else f"checkbox_p{pi+1}_{round(cb['top'])}")
            
            name_counts[name] = name_counts.get(name, 0) + 1
            if name_counts[name] > 1:
                name = f"{name}_{name_counts[name]}"

            all_fields.append({
                "page": pi,
                "kind": "checkbox",
                "name": name,
                "rect": [cb["x0"], cb["top"], cb["x1"], cb["bottom"]],
                "tooltip": f"Checkbox - {label}"
            })

        # 2b. Process grouped Comb Fields
        for cf in comb_fields:
            # Find labels near this comb field
            left_words = []
            below_words = []
            for w in words:
                if abs(w["top"] - cf["top"]) < 8.0 and w["x1"] < cf["x0"] and cf["x0"] - w["x1"] < 120.0:
                    left_words.append(w)
                elif cf["bottom"] <= w["top"] <= cf["bottom"] + 15.0 and cf["x0"] - 5.0 <= w["x0"] <= cf["x1"] + 5.0:
                    below_words.append(w)

            left_str = " ".join([w["text"] for w in sorted(left_words, key=lambda x: x["x0"])])
            below_str = " ".join([w["text"] for w in sorted(below_words, key=lambda x: x["x0"])])

            label_parts = []
            if left_str:
                label_parts.append(left_str)
            if below_str:
                label_parts.append(below_str)

            full_label = " - ".join([p for p in label_parts if p])
            tooltip = f"Enter {full_label}" if full_label else f"Segmented entry ({cf['count']} cells)"

            clean_left = clean_name(left_str)
            clean_below = clean_name(below_str)

            if clean_left and clean_below:
                name = f"{clean_left}_{clean_below}"
            elif clean_below:
                name = clean_below
            elif clean_left:
                name = clean_left
            else:
                name = f"comb_p{pi+1}_{round(cf['top'])}"

            name = clean_name(name)
            name_counts[name] = name_counts.get(name, 0) + 1
            if name_counts[name] > 1:
                name = f"{name}_{name_counts[name]}"

            all_fields.append({
                "page": pi,
                "kind": "comb",
                "name": name,
                "rect": [cf["x0"], cf["top"], cf["x1"], cf["bottom"]],
                "tooltip": tooltip,
                "maxlen": cf["count"]
            })

        # 3. Process Underlines and Grid Borders
        for ul in unique_underlines:
            ux0, utop, ux1, ubottom = ul["x0"], ul["top"], ul["x1"], ul["bottom"]
            uw = ux1 - ux0

            # A. Filter out massive page-spanning section dividers
            if uw > max_line_width or uw > page_width * 0.8:
                continue

            # B. Check if there are words written INSIDE the area just above this line
            # This identifies whether this area is a LABEL cell.
            words_inside = []
            words_just_below = []
            for w in words:
                # words written above the line
                if utop - collision_height <= w["top"] < utop and ux0 - collision_padding <= w["x0"] <= ux1 + collision_padding:
                    words_inside.append(w)
                # words written below the line (within 15 points)
                elif utop <= w["top"] < utop + 15.0 and ux0 - 2.0 <= w["x0"] <= ux1 + 2.0:
                    words_just_below.append(w)

            words_inside = sorted(words_inside, key=lambda x: x["x0"])
            words_just_below = sorted(words_just_below, key=lambda x: x["x0"])

            # If there is printed text inside the field area, it is a Label Cell! Do NOT place a field here.
            # But wait: if the text is very short (like "M.I.") and on the left, it might be an inline label.
            # Let us calculate the text length and area to see if it is a major label.
            inside_text = " ".join([w["text"] for w in words_inside])
            if inside_text and len(inside_text) > 4 and any(c.isalpha() for c in inside_text):
                # This is a printed label cell, skip it!
                continue

            # C. Detect side-by-side multiple labels below a single horizontal line
            # (e.g., "First Name    MI    Last Name" horizontally split)
            label_groups = []
            current_group = []
            for w in words_just_below:
                # Filter out numbers or checkbox labels like "Yes No"
                if not any(c.isalpha() for c in w["text"]):
                    continue
                if current_group and w["x0"] - current_group[-1]["x1"] > 25.0:
                    label_groups.append(current_group)
                    current_group = [w]
                else:
                    current_group.append(w)
            if current_group:
                label_groups.append(current_group)

            # Let us see if we should split this line!
            if len(label_groups) > 1:
                # Split the horizontal line based on label horizontal coordinates!
                for idx, grp in enumerate(label_groups):
                    grp_label = " ".join([w["text"] for w in grp])
                    grp_x0 = grp[0]["x0"]
                    # Span until the start of the next group, or the end of the line
                    grp_x1 = label_groups[idx+1][0]["x0"] - 10.0 if idx + 1 < len(label_groups) else ux1
                    # Ensure coordinates are within line bounds
                    grp_x0 = max(ux0, grp_x0)
                    grp_x1 = min(ux1, grp_x1)

                    if grp_x1 - grp_x0 > 15.0:
                        name = clean_name(grp_label)
                        name_counts[name] = name_counts.get(name, 0) + 1
                        if name_counts[name] > 1:
                            name = f"{name}_{name_counts[name]}"

                        all_fields.append({
                            "page": pi,
                            "kind": "text",
                            "name": name,
                            "rect": [grp_x0, utop - 12.0, grp_x1, utop],
                            "tooltip": f"Enter {grp_label}"
                        })
                continue

            # D. Standard Single Input Line/Cell
            below_str = " ".join([w["text"] for w in words_just_below if any(c.isalpha() for c in w["text"])])
            
            # Find words on the same line to the left
            left_words = []
            for w in words:
                if abs(w["top"] - utop) < 10.0:
                    if w["x1"] < ux0 and ux0 - w["x1"] < 120.0:
                        left_words.append(w)
            left_str = " ".join([w["text"] for w in sorted(left_words, key=lambda x: x["x0"])])

            label_parts = []
            if left_str:
                label_parts.append(left_str)
            if below_str:
                label_parts.append(below_str)

            full_label = " - ".join([p for p in label_parts if p])
            tooltip = f"Enter {full_label}" if full_label else "Text input"

            clean_left = clean_name(left_str)
            clean_below = clean_name(below_str)

            if clean_left and clean_below:
                base_name = f"{clean_left}_{clean_below}"
            elif clean_below:
                base_name = clean_below
            elif clean_left:
                base_name = clean_left
            else:
                base_name = f"text_line_page_{pi+1}_{round(utop)}"

            name = clean_name(base_name)
            name_counts[name] = name_counts.get(name, 0) + 1
            if name_counts[name] > 1:
                name = f"{name}_{name_counts[name]}"

            all_fields.append({
                "page": pi,
                "kind": "text",
                "name": name,
                "rect": [ux0, utop - 12.0, ux1, utop],
                "tooltip": tooltip
            })

    # Also handle boxed cells (like on the UWV and Cerfa forms)!
    # Let us identify rects that are actual empty input boxes (height 10 to 30, width > 20)
    for pi, page in enumerate(pdf.pages):
        words = page.extract_words()
        rects = page.rects
        
        for r in rects:
            x0, x1, top, bottom = round(r["x0"], 1), round(r["x1"], 1), round(r["top"], 1), round(r["bottom"], 1)
            w, h = x1 - x0, bottom - top
            
            # Identify standard single-line box cells vs. multiline comment areas
            is_single_line = 20 <= w <= 450 and 10 <= h <= 25
            is_multiline = 50 <= w <= 500 and 25 < h <= 250
            
            if is_single_line or is_multiline:
                # Check if we already have a text field overlapping this rect closely
                already_covered = False
                for f in all_fields:
                    if f["page"] == pi:
                        fx0, ftop, fx1, fbottom = f["rect"]
                        # if overlap is significant
                        overlap_x = max(0, min(x1, fx1) - max(x0, fx0))
                        overlap_y = max(0, min(bottom, fbottom) - max(top, ftop))
                        if overlap_x > 10 and overlap_y > 5:
                            already_covered = True
                            break
                if already_covered:
                    continue

                # Check if there are words written INSIDE this rect
                words_inside = []
                for w_item in words:
                    if top + 1.0 <= w_item["top"] <= bottom - 1.0 and x0 + 2.0 <= w_item["x0"] <= x1 - 2.0:
                        words_inside.append(w_item)
                
                inside_text = " ".join([w_item["text"] for w_item in sorted(words_inside, key=lambda x: x["x0"])])
                if inside_text and len(inside_text) > 8 and any(c.isalpha() for c in inside_text):
                    # Printed label box, not input box!
                    continue

                # Find labels near this box (above, below, or to the left)
                below_words = []
                left_words = []
                above_words = []
                for w_item in words:
                    if bottom <= w_item["top"] <= bottom + 15.0 and x0 - 2.0 <= w_item["x0"] <= x1 + 2.0:
                        below_words.append(w_item)
                    elif abs(w_item["top"] - top) < 8.0 and w_item["x1"] < x0 and x0 - w_item["x1"] < 120.0:
                        left_words.append(w_item)
                    elif top - 15.0 <= w_item["top"] < top and x0 - 2.0 <= w_item["x0"] <= x1 + 2.0:
                        above_words.append(w_item)

                below_str = " ".join([w_item["text"] for w_item in sorted(below_words, key=lambda x: x["x0"]) if any(c.isalpha() for c in w_item["text"])])
                left_str = " ".join([w_item["text"] for w_item in sorted(left_words, key=lambda x: x["x0"]) if any(c.isalpha() for c in w_item["text"])])
                above_str = " ".join([w_item["text"] for w_item in sorted(above_words, key=lambda x: x["x0"]) if any(c.isalpha() for c in w_item["text"])])

                label_parts = []
                if above_str:
                    label_parts.append(above_str)
                elif left_str:
                    label_parts.append(left_str)
                elif below_str:
                    label_parts.append(below_str)

                full_label = " - ".join([p for p in label_parts if p])
                tooltip = f"Enter {full_label}" if full_label else ("Multiline area" if is_multiline else "Text box")

                clean_name_base = clean_name(above_str if above_str else (left_str if left_str else (below_str if below_str else f"textbox_page_{pi+1}_{round(top)}")))
                name = clean_name(clean_name_base)
                name_counts[name] = name_counts.get(name, 0) + 1
                if name_counts[name] > 1:
                    name = f"{name}_{name_counts[name]}"

                field_spec = {
                    "page": pi,
                    "kind": "text",
                    "name": name,
                    "rect": [x0, top, x1, bottom],
                    "tooltip": tooltip
                }
                if is_multiline:
                    field_spec["multiline"] = True
                    
                all_fields.append(field_spec)

    with open(output_spec, "w") as f:
        json.dump(all_fields, f, indent=1)

    print(f"V2: Successfully auto-generated {len(all_fields)} fields in {output_spec}")

if __name__ == "__main__":
    main()
