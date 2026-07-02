#!/usr/bin/env python3
"""
process_form.py

Runs the complete PDF form-builder pipeline for a given input PDF.
Outputs all intermediate and final files to a specified output directory.

Workflow:
  1. Auto-generate field_spec.json (unless a custom one already exists)
     Supports different layout-extraction sensitivities (low, medium, high, or all)
  2. Derive correct geometric tab order to produce field_spec_ordered.json
  3. Build the fillable PDF form as output.pdf
  4. Auto-generate dummy sample_data.json
  5. Fill form with sample data and render pages as PNGs to verify_out/
"""
import sys
import os
import json
import argparse
import subprocess

def run_single_pipeline(input_pdf, output_dir, custom_spec=None, sensitivity="medium"):
    print(f"\n--- Running Extraction Level: {sensitivity.upper()} ---")
    os.makedirs(output_dir, exist_ok=True)

    # Define paths
    spec_path = os.path.join(output_dir, "field_spec.json")
    ordered_spec_path = os.path.join(output_dir, "field_spec_ordered.json")
    output_pdf_path = os.path.join(output_dir, "output.pdf")
    name_map_path = os.path.join(output_dir, "name_map.json")
    sample_data_path = os.path.join(output_dir, "sample_data.json")
    verify_out_dir = os.path.join(output_dir, "verify_out")

    # 1. Get/generate field spec
    if custom_spec and os.path.exists(custom_spec):
        print(f"Using provided custom field spec: {custom_spec}")
        subprocess.run(["cp", custom_spec, spec_path], check=True)
    elif os.path.exists(spec_path):
        print(f"Re-using existing field spec: {spec_path}")
    else:
        print(f"Auto-generating field specification draft with sensitivity={sensitivity}...")
        subprocess.run([
            "python", "scripts/auto_generate_spec.py",
            input_pdf, spec_path,
            "--sensitivity", sensitivity
        ], check=True)

    # 2. Derive Tab Order
    print("Deriving optimal tab order from geometry...")
    subprocess.run([
        "python", "scripts/derive_field_order.py",
        spec_path, ordered_spec_path
    ], check=True)

    # 3. Build fillable PDF
    print("Building fillable AcroForm PDF...")
    subprocess.run([
        "python", "scripts/build_form.py",
        input_pdf, ordered_spec_path, output_pdf_path
    ], check=True)

    # 4. Auto-generate sample data for visual verification
    if not os.path.exists(sample_data_path):
        print("Generating mock sample data for verification...")
        ordered_fields = json.load(open(ordered_spec_path))
        mock_data = {}
        for f in ordered_fields:
            name = f["name"]
            if f["kind"] == "checkbox":
                mock_data[name] = "/Yes"
            elif f["kind"] == "comb":
                maxlen = f.get("maxlen", 8)
                mock_data[name] = "12345678901234567890"[:maxlen]
            else:
                # Text: use clean truncated field name
                mock_data[name] = name.replace("_", " ")[:20]
        with open(sample_data_path, "w") as f:
            json.dump(mock_data, f, indent=1)

    # 5. Fill and Verify (render PNGs)
    print("Filling form and rendering visual verification PNGs...")
    subprocess.run([
        "python", "scripts/verify_fill.py",
        output_pdf_path, name_map_path, sample_data_path, verify_out_dir
    ], check=True)

    print(f"Extraction Level {sensitivity.upper()} completed successfully!")
    print(f"Outputs written to: {output_dir}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_pdf")
    ap.add_argument("output_dir")
    ap.add_argument("custom_field_spec", nargs="?", default=None, 
                    help="Optional hand-crafted field specification JSON")
    ap.add_argument("--sensitivity", "-s", choices=["low", "medium", "high", "all"], default="medium",
                    help="Sensitivity level of layout extraction (or 'all' to compile all 3 for side-by-side comparison)")
    args = ap.parse_args()

    input_pdf = args.input_pdf
    output_dir = args.output_dir
    custom_spec = args.custom_field_spec
    sensitivity = args.sensitivity

    print(f"=========================================================")
    print(f"=== Starting master pipeline for: {os.path.basename(input_pdf)} ===")
    print(f"=========================================================")

    if sensitivity == "all":
        print("Sensitivity parameter set to ALL. Compiling Low, Medium, and High sensitivity versions...")
        for level in ["low", "medium", "high"]:
            level_dir = os.path.join(output_dir, level)
            run_single_pipeline(input_pdf, level_dir, custom_spec, sensitivity=level)
    else:
        run_single_pipeline(input_pdf, output_dir, custom_spec, sensitivity=sensitivity)

    print(f"\n=========================================================")
    print(f"=== Master pipeline completed successfully! ===")
    print(f"=========================================================")

if __name__ == "__main__":
    main()
