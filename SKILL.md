# PDF Form Fixer — turning flat/non-fillable PDFs into real AcroForms

## Two ways to use this repo

This repo is both things at once, deliberately:

1. **A plain command-line toolkit.** `scripts/*.py` are ordinary,
   self-contained Python scripts. Clone the repo, `pip install -r
   requirements.txt`, and run them from a terminal like any other tool —
   no Claude involved at all.

2. **A [Claude Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview).**
   `SKILL.md` (this file) is written as instructions *addressed to
   Claude* — if you drop this whole folder somewhere Claude's Skills
   feature can discover it (Claude Code, Claude.ai/Claude Cowork with
   Skills enabled, or the Claude Agent SDK), Claude will read this file
   on its own when a task matches and drive `scripts/*.py` itself,
   following the procedure below.

Nothing in this repo depends on any path specific to Anthropic's
infrastructure (no `/mnt/...` or similar) — every script only ever reads
paths you pass it on the command line.

## When to use this skill

Use this whenever a PDF form has no fillable fields (confirm with
`scripts/check_fillable_fields.py`) but has a clear printed layout —
entry lines, tick-box grids for numbers/dates, checkbox glyphs — and the
person wants to actually *fill it in on a computer* rather than print and
handwrite it.

This is common with:
- Government/immigration forms (the original use case: an IND — Dutch
  immigration service — declaration form)
- Insurance and benefits forms
- Older forms exported from InDesign/LaTeX/Word to PDF without an AcroForm

This is a *different* task from filling fields that already exist — if
`check_fillable_fields.py` says the PDF already has fields, just fill
those directly with any standard PDF library instead of using this
toolkit.

## Why this needs its own workflow

Three mistakes are easy to make and easy to miss until someone actually
tries to use the form:

1. **Guessing coordinates from a rendered image is not accurate enough.**
   Eyeballing a PNG render of the page and estimating box positions will
   be close but visibly off. The PDF's underlying vector rectangles and
   lines are exact — always read `page.rects` / `page.lines` (pdfplumber)
   directly rather than estimating from pixels. That's what
   `extract_geometry.py` does.

2. **Segmented number/date boxes want ONE comb field, not N separate
   fields.** A row of 8 tick-boxes for `DD MM YYYY` should be a single
   text field with the PDF "Comb" flag set and `MaxLen=8` — the viewer
   auto-spaces each typed character into its own cell. Creating 8 separate
   1-character fields technically works but is worse UX (the person has to
   manually Tab between every single digit) and is *also* the direct cause
   of problem 3 below.

3. **Tab order must be derived from geometry, not hand-typed, and then
   baked into the field names.** Hand-authoring field order is exactly the
   kind of thing that's easy to get subtly wrong when a form has 40+
   fields across several pages (we proved this twice on the reference
   example). Worse: some PDF viewers, especially on **tagged/accessible
   PDFs** (`/MarkInfo /Marked true` + a `/StructTreeRoot` — common on
   government forms for WCAG compliance), fall back to sorting fields
   *alphabetically by internal field name* when they can't cleanly resolve
   structure-tree tab order for newly-added widgets. The fix that's robust
   across viewers: derive the correct order purely from field geometry
   (row-cluster top-to-bottom, then left-to-right within a row, via
   `derive_field_order.py`), and give every field a zero-padded sequence
   prefix in its actual PDF name (`007_sex_male`) so the annotation order
   *and* the alphabetical order agree.

## How general is this?

The **mechanics** here are fully general and will work on any flat PDF
form that draws its lines/boxes as real vector graphics (the large
majority of generated — as opposed to scanned — forms):
- reading exact geometry instead of guessing,
- comb fields for segmented cells,
- geometry-derived tab order with sequence-prefixed names,
- generated checkbox appearance streams,
- a mandatory fill-and-render verification loop.

What does **not** generalize automatically is the semantic step: deciding
*this* printed line is a text field, *this* row of ticks is a comb field
for a date, *this* glyph means "Male". That requires reading the form and
understanding its meaning — inherently a job for Claude (or a human) to
do per-form, not a script. This toolkit packages the mechanical parts as
reusable scripts (`scripts/`) and documents the semantic step as a guided
procedure below.

If the source PDF is a **scanned/rasterized image** with no real vector
lines at all, `extract_geometry.py` will come back empty — this toolkit
won't help directly. In that case you'd need a purely pixel-based
approach instead: render pages to images, visually locate box positions,
and work in pixel space converted to PDF points. That's a meaningfully
different workflow (no vector ground truth to check against) and isn't
covered here.

## Procedure

### 0. Diagnose

```bash
python scripts/check_fillable_fields.py <input.pdf>
```

Confirms there's no existing AcroForm to fill instead.

### 1. Extract exact geometry

```bash
python scripts/extract_geometry.py <input.pdf> geometry.json
python scripts/render_pages.py <input.pdf> rendered_pages/
```

Look at the rendered PNGs to read the form normally while cross-referencing
`geometry.json` for exact coordinates.

### 2. Auto-generate the field spec draft (The AI-Assisted Bootstrap Step)

Instead of writing hundreds of field coordinates by hand, bootstrap your specification by running:

```bash
python scripts/auto_generate_spec.py <input.pdf> field_spec.json
```

This advanced script uses geometric and semantic heuristics to auto-generate a drafted spec:
- **Grid-Cell Word Collision Filtering**: Identifies when printed text is written inside a cell boundary (e.g. static labels like "Date of birth" or section titles), and automatically skips generating input fields over them to prevent covering static text.
- **Underline Label Splitting**: Detects when a single long physical vector line represents multiple distinct fields side-by-side (e.g. "First Name   MI   Last Name"), and splits the line into perfectly aligned separate text fields.
- **Box-Cell Identification**: Scans for standard rectangular vector boxes (height ~12-25pt) where user inputs should reside, skipping printed label borders and visual divider borders.
- **Text-Symbol Checkbox/Underline Parsing**: Extracts standard typographical characters (☐, ☑, underscores `_____`, and dotted lines `.......`) when forms don't draw vector lines.

### 3. Programmatic Overlap Diagnostics & Manual Polish (MANDATORY — NEVER SKIP)

Because form authors employ wild and irregular layout/drawing conventions, **auto-generation is a draft, not the final product**. You **must** systematically evaluate and iterate on the spec:

#### Step A: Run Programmatic Diagnostics
Run the overlap diagnostic tool to immediately find any text fields that are directly covering up or overlapping static labels:

```bash
python scripts/diagnose_overlapping_fields.py <input.pdf> <field_spec.json>
```

This utility scans every field bounding box against standard text words and outputs a detailed list of all overlaps (e.g. `Field 005 (text) overlaps static text: "Date of application:"`).

#### Step B: Tweak the Auto-Generator Parameters
If the form uses non-standard dimensions, you can tweak the core parameters inside `scripts/auto_generate_spec.py` to let the AI do better:
- **Comb Spacing (`gap <= 4.0pt`)**: Lower this threshold to split boxes (e.g. keep postcode segments open); raise it to merge widely spaced postcode letters.
- **Word Collision Bounds (`utop - 15.5pt`)**: Increase this to `18.0pt` or `20.0pt` if static table labels are still being covered by text fields.
- **Visual Divider Width (`width > 450pt`)**: Adjust this to filter out larger border lines or page frame rectangles.

#### Step C: Surgical Review & Manual Spec Polish
Surgically adjust the remaining 5–10 visual edge cases inside `field_spec.json` (such as deleting unwanted decorative border lines, setting custom `maxlen` values on segmented groups, or adjusting a width) to achieve visual perfection.

See `examples/tb_declaration/field_spec.json` for a reference 42-field specification that achieves perfect production alignment.

### 4. Derive tab order (mandatory — never hand-order fields)

```bash
python scripts/derive_field_order.py field_spec.json field_spec_ordered.json
```

Review the printed order report. If a field lands in the wrong row-cluster (e.g. two fields visually on different rows get grouped together), adjust `--tolerance` or fix that field's `rect` in the spec and re-run.

### 5. Build the fillable PDF

```bash
python scripts/build_form.py source.pdf field_spec_ordered.json output.pdf
```

This also writes `name_map.json` next to the output (short field name → actual sequence-prefixed PDF field name), which you'll use for programmatic filling.

### 6. Verify — mandatory, not optional

```bash
python scripts/verify_fill.py output.pdf name_map.json sample_data.json verify_out/
```

Then **actually view the rendered PNGs in `verify_out/`**:
- Does every value sit perfectly inside its printed line/box without overlapping static text?
- Are checkboxes showing a visible mark when checked?
- Open the real PDF in a viewer and Tab through it — does focus follow the reading order?

If anything is off, fix the coordinates or entries in `field_spec.json` and rebuild — steps 4–6 are cheap to re-run.

`sample_data.json` is `{"logical_name": "value", ...}` using the short
names from your field spec — check off checkboxes with `"/Yes"`. Then
**actually view the rendered PNGs**:

- Does every value sit inside its printed line/box, not overlapping
  static text?
- For comb fields: does each character land in its own printed cell?
- Do checked checkboxes show a visible mark?
- Open the real PDF in a viewer and Tab through it — does focus follow
  reading order, especially across checkbox ↔ text-field transitions and
  page boundaries?

If anything is off, fix the field spec (not the output PDF directly) and
rebuild — steps 3–5 are cheap to re-run.

## Known limitations

- Tab-order behavior can still vary slightly between PDF viewers even
  with sequence-prefixed names — Adobe Acrobat Reader is the most
  spec-compliant reference implementation; lighter-weight viewers
  (browser built-ins, Preview) are more likely to have their own
  heuristics.
- Some very lightweight PDF viewers don't honor `/NeedAppearances` for
  text-field rendering. The generated checkbox appearance streams don't
  have this problem (they're baked in directly), but a plain text field's
  typed value may not render until saved/exported in a handful of minimal
  viewers. Recommend Adobe Acrobat Reader (free) if the person reports
  blank-looking fields.
- Only tested against forms with a single-column layout (one field per
  visual row). Multi-column forms should still work with the row-cluster
  + left-to-right logic in `derive_field_order.py`, but haven't been
  validated against one — check the order report carefully in that case.
- `extract_geometry.py`'s checkbox-glyph detection covers the Private Use
  Area convention (most common) but you should also scan `words` for
  plain Unicode box-drawing characters (☐ ☑ □ ✓ ✗) — some forms
  (e.g. French Cerfa forms) use those instead.
