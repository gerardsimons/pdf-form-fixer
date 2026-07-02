#!/usr/bin/env python3
"""
process_form.py

Runs the complete PDF form-builder pipeline for a given input PDF.
Outputs all intermediate and final files to a specified output directory.

Workflow:
  1. Auto-generate field_spec.json (unless a custom one already exists)
  2. Derive correct geometric tab order to produce field_spec_ordered.json
  3. Build the fillable PDF form as output.pdf
  4. Auto-generate dummy sample_data.json
  5. Fill form with sample data and render pages as PNGs to verify_out/
"""
import sys
import os
import json
import subprocess

def main():
    if len(sys.argv) < 3:
        print("Usage: python process_form.py <input.pdf> <output_dir> [custom_field_spec.json]")
        sys.exit(1)

    input_pdf = sys.argv[1]
    output_dir = sys.argv[2]
    custom_spec = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"=== Starting pipeline for: {os.path.basename(input_pdf)} ===")
    print(f"Output Directory: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Define paths
    spec_path = os.path.join(output_dir, "field_spec.json")
    ordered_spec_path = os.path.join(output_dir, "field_spec_ordered.json")
    output_pdf_path = os.path.join(output_dir, "output.pdf")
    name_map_path = os.path.join(output_dir, "name_map.json")
    sample_data_path = os.path.join(output_dir, "sample_data.json")
    verify_out_dir = os.path.join(output_dir, "verify_out")

    # 2. Get/generate field spec
    if custom_spec and os.path.exists(custom_spec):
        print(f"Using provided custom field spec: {custom_spec}")
        subprocess.run(["cp", custom_spec, spec_path], check=True)
    elif os.path.exists(spec_path):
        print(f"Re-using existing field spec: {spec_path}")
    else:
        print("Auto-generating field specification draft...")
        subprocess.run([
            "python", "scripts/auto_generate_spec.py",
            input_pdf, spec_path
        ], check=True)

    # 3. Derive Tab Order
    print("Deriving optimal tab order from geometry...")
    subprocess.run([
        "python", "scripts/derive_field_order.py",
        spec_path, ordered_spec_path
    ], check=True)

    # 4. Build fillable PDF
    print("Building fillable AcroForm PDF...")
    # build_form.py writes name_map.json in its current directory or next to output.
    # Wait! Let us run build_form.py with the correct path.
    # Note: build_form.py writes name_map.json in the directory of output_pdf.
    # Let us verify if build_form.py takes output path as parameter. Yes!
    subprocess.run([
        "python", "scripts/build_form.py",
        input_pdf, ordered_spec_path, output_pdf_path
    ], check=True)

    # Move name_map.json to output directory if it is written in current directory
    # build_form.py has: open(os.path.join(os.path.dirname(args.output_pdf), "name_map.json"))
    # So name_map.json will naturally be created in output_dir.

    # 5. Auto-generate sample data for visual verification
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

    # 6. Fill and Verify (render PNGs)
    print("Filling form and rendering visual verification PNGs...")
    subprocess.run([
        "python", "scripts/verify_fill.py",
        output_pdf_path, name_map_path, sample_data_path, verify_out_dir
    ], check=True)

    print(f"=== Pipeline completed successfully for {os.path.basename(input_pdf)} ===")
    print(f"Outputs written to: {output_dir}\n")

if __name__ == "__main__":
    main()
