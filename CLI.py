#!/usr/bin/env python3
"""
CLI.py

The unified Command-Line Interface for the PDF Form Fixer toolkit.
Wraps the entire workflow into a single user-friendly CLI with built-in
multi-sensitivity pipelines and overlap/alignment debug metrics.
"""
import argparse
import sys
import os
import subprocess

def main():
    ap = argparse.ArgumentParser(description="Unified CLI for turning flat, non-fillable PDF forms into fillable AcroForms.")
    ap.add_argument("input_pdf", help="Path to the flat input PDF form")
    ap.add_argument("output_dir", help="Path to the directory where outputs should be saved")
    ap.add_argument("-c", "--custom-spec", default=None, help="Optional hand-crafted field_spec.json to bypass auto-generation")
    ap.add_argument("-s", "--sensitivity", choices=["low", "medium", "high", "all"], default="medium",
                    help="Sensitivity level of layout extraction (low=conservative, medium=balanced, high=greedy, all=run all three side-by-side)")
    ap.add_argument("-d", "--debug", action="store_true", help="Print advanced layout-analysis & collision overlap metrics for visual alignment check")
    args = ap.parse_args()

    input_pdf = args.input_pdf
    output_dir = args.output_dir
    custom_spec = args.custom_spec
    sensitivity = args.sensitivity
    debug = args.debug

    # Make output_dir absolute for safety
    output_dir = os.path.abspath(output_dir)

    # 1. Run the main process orchestrator
    print("""
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
""")
    print(f"=========================================================")
    print(f"=========================================================")
    print(f"Input PDF:  {input_pdf}")
    print(f"Output Dir: {output_dir}")
    print(f"Sensitivity: {sensitivity.upper()}")
    print(f"Debug Mode:  {'ENABLED' if debug else 'DISABLED'}")
    print(f"=========================================================\n")

    cmd = ["python", "scripts/process_form.py", input_pdf, output_dir]
    if custom_spec:
        cmd.append(custom_spec)
    
    cmd.extend(["--sensitivity", sensitivity])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[Error] Pipeline execution failed: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. If debug is set, execute diagnostics and report metrics
    if debug:
        print("\n=========================================================")
        print(f"===               ALIGNMENT DIAGNOSTICS               ===")
        print(f"=========================================================")
        
        if sensitivity == "all":
            for level in ["low", "medium", "high"]:
                level_dir = os.path.join(output_dir, level)
                level_spec = os.path.join(level_dir, "field_spec_ordered.json")
                if os.path.exists(level_spec):
                    print(f"\n--- Overlap Diagnostics for sensitivity={level.upper()} ---")
                    subprocess.run(["python", "scripts/diagnose_overlapping_fields.py", input_pdf, level_spec])
        else:
            ordered_spec = os.path.join(output_dir, "field_spec_ordered.json")
            if os.path.exists(ordered_spec):
                subprocess.run(["python", "scripts/diagnose_overlapping_fields.py", input_pdf, ordered_spec])
        print("=========================================================\n")

    print("\n[Success] Form processing complete!")

if __name__ == "__main__":
    main()
