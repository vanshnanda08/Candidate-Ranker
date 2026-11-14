"""Write a small, wholly fictional local dataset for the dashboard demo."""
import argparse
import json
from pathlib import Path


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.demo_data import four_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    rows = four_candidates()
    # Refuse to overwrite any existing candidate file, including the user's data.
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2)
    print(f"Wrote {len(rows)} fictional profiles to {args.out}")


if __name__ == "__main__":
    main()
