```text
  ____  ____  _____   _____ ___  ____  __  __ 
 |  _ \|  _ \|  ___| |  ___/ _ \|  _ \|  \/  |
 | |_) | | | | |_    | |_ | | | | |_) | |\/| |
 |  __/| |_| |  _|   |  _|| |_| |  _ <| |  | |
 |_|   |____/|_|     |_|   \___/|_| \_\_|  |_|
  _____  _  __  __ _____ ____  
 |  ___|| | \ \/ /|  ___|  _ \ 
 | |_   | |  \  / | |_  | |_) |
 |  _|  | |  /  \ |  _| |  _ < 
 |_|    |_| /_/\_\|_____|_| \_\
```

# pdf-form-fixer

A [Claude/Gemini Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
*and* a plain standalone toolkit (it's both — see `SKILL.md`) for turning
flat, non-fillable PDF forms into real, typeable AcroForm PDFs — with
correct comb-field number/date entry and correct Tab order, including on
tagged/accessible government forms where that's surprisingly easy to get
wrong.

Built from real worked examples: Dutch immigration (IND) and UWV declaration forms, standard Job Applications, and French Cerfa forms.

## Why?

AI is busy revolutionizing molecular biology, solving quantum physics, automating software engineering, and reshaping the future of humanity. But sometimes... you just want a functioning, typeable PDF form so you don't have to print, handwrite, and scan a 10-page document like it's 1999. 

With all the state-of-the-art AI models at our disposal, we were still struggling with annoying Dutch PDF "forms" that were not real forms. That is why we built this. You're welcome, governments and government users around the world!

### ⚠️ Vibecoding Warning
This entire toolkit has been aggressively and lovingly **vibecoded** (vibe-coded) in partnership with Gemini CLI. It is built on pure intuition, late-night visual coordinates-shifting, and chaotic layout-analysis hacks. 

**Contributions (especially highly vibecoded ones) are extremely welcome!** If you drop a messy flat PDF in here, run into some weird visual edge-cases, and fix them with your own vibe-coded heuristics, please submit a PR!

## Contents

```
SKILL.md                        Expert Gemini Skill procedure and design rationale
scripts/
  check_fillable_fields.py      Step 0: confirm the PDF needs this at all
  extract_geometry.py           Read exact vector geometry (rects, lines, labels, checkbox glyphs)
  auto_generate_spec.py         Advanced layout analysis & semantic specification draft generator
  process_form.py               End-to-end pipeline orchestrator (bootstrap -> compile -> fill -> render)
  diagnose_overlapping_fields.py Overlap & collision checking diagnostics utility
  derive_field_order.py         Geometry-derived tab order + sequence-prefixed field names
  build_form.py                 Build the AcroForm (text / comb / checkbox / multiline fields)
  verify_fill.py                Fill with sample data + render to PNG for mandatory verification
```

## Quick Start (Automated Bootstrap Pipeline)

To run any flat PDF through our advanced layout-analysis bootstrap pipeline:

```bash
pip install -r requirements.txt

# Process a form from start to finish
python scripts/process_form.py sample_forms/Job_Application_Form_Lima.pdf output/job_application_lima/

# Run programmatic overlap diagnostics to find fields covering static text
python scripts/diagnose_overlapping_fields.py sample_forms/Job_Application_Form_Lima.pdf output/job_application_lima/field_spec_ordered.json
```

This generates **Red-colored pre-filled placeholder text** inside **`output/<form_name>/output.pdf`** and renders visual page PNGs in **`output/<form_name>/verify_out/`** for instant visual checking!

---

## Form Typologies: What Makes Forms "Messy"?

Flat PDF forms are designed for humans to print and fill by hand, meaning they lack uniform digital structures. They generally fall into two broad typologies:

### 1. Vector-Heavy Grid Forms (e.g., Dutch Forms)
Forms designed by Dutch organizations (like IND and UWV) are characterized by **high geometric consistency** and explicit vector boxes:
- **Hollow Vector Boxes**: Fields are drawn as actual vector rectangles (`page.rects`) of height ~15–20pt.
- **PUA Checkbox Glyphs**: Checkboxes are drawn using specific font-character glyphs in the Unicode Private Use Area (PUA) like `0xE000-0xF8FF` (making them mathematically distinct from plain text).
- **Contiguous Touching Boxes**: Date, Postcode, and BSN fields are made of rows of contiguous small square boxes.
- **Why they work so well**: Because the grid and boxes are drawn as exact mathematical shapes, our geometric heuristics can extract and map them with pixel-perfect precision out-of-the-box.

### 2. Typographic-Heavy Forms (e.g., French Cerfa Forms)
Forms designed in other standard offices (like French Cerfa or general Microsoft Word exports) rely heavily on **standard typography characters** instead of vector drawings:
- **Text Underlines**: Underlines are drawn using strings of standard underscores (`_______`) or dotted characters (`.......`) embedded directly in the text words.
- **Text Checkboxes**: Checkboxes are drawn as plain Unicode ballot box characters (☐, ☑, □, ■) or text brackets (`[ ]`).
- **Visual Page Dividers**: Borders and section divisions are drawn as long, thin horizontal lines that can span the entire content column, mimicking underlines.
- **Why they are tricky**: Because the checkboxes and underlines are normal text characters, purely vector-based parsers are completely blind to them. They require a hybrid parser (`auto_generate_spec.py`) that matches standard text symbols and handles table-cell bounding collisions.

---

## How to Tweak the AI/Heuristics to Do Better

If an auto-generated form has misplaced, overlapping, or missing fields, you can tweak the following core layout-analysis parameters in `scripts/auto_generate_spec.py`:

1. **Comb Spacing and Segment Splits** (`current_group and cb["x0"] - ... > 4.0`):
   - By default, squares are grouped into a `comb` field if their gap is $\le 4.0\text{pt}$. This ensures postcode and DOB blocks are cleanly split at dashes/spaces.
   - If a form has widely spaced postcode letters, increase this threshold (e.g. to `10.0`) to keep them in a single comb.

2. **Word Collision Vertical Bounds** (`utop - 15.5 <= w["top"] < utop`):
   - This prevents overlapping static labels. By default, it checks up to `15.5pt` above any line.
   - If text headers are still being covered, increase this to `18.0` or `20.0`. If legitimate input lines under very tight rows are being skipped, lower this to `12.0`.

3. **Section Divider Width Filter** (`uw > 450.0 or uw > page_width * 0.8`):
   - To ignore page frame borders and section dividing lines, we filter out horizontal lines wider than `450pt`.
   - On landscape forms, or forms with ultra-wide full-width comments fields, raise this threshold to `550.0`.

4. **Red Visual Verification Highlights**:
   - `build_form.py` colors all filled text **Red** (`/DA /Helv Tf 1 0 0 rg`). This makes it immediately obvious when text baseline alignments, margins, or heights are slightly off in your rendered PNG previews.

---

## License

MIT (adjust as you like — this is a starting point for your own repo).
