#!/usr/bin/env python3
"""
merge_json_lists.py
-------------------

Merge two JSON files containing JSON arrays into a single JSON file.

Usage:
    python merge_json_lists.py input_file_1.json input_file_2.json output_file.json

Notes:
  • Both input files must contain a JSON list at the top level.
  • The output file will contain the concatenation:
        input_file_1 + input_file_2
  • No deduplication or sorting is performed.
"""

import json
import sys
from pathlib import Path


def load_json_list(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} does not contain a JSON list")
    return data


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python merge_json_lists.py "
            "input_file_1.json input_file_2.json output_file.json",
            file=sys.stderr,
        )
        sys.exit(1)

    input_file_1 = Path(sys.argv[1])
    input_file_2 = Path(sys.argv[2])
    output_file = Path(sys.argv[3])

    list1 = load_json_list(input_file_1)
    list2 = load_json_list(input_file_2)

    merged = list1 + list2

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(
        f"Merged {len(list1)} + {len(list2)} "
        f"items → {len(merged)} items into {output_file}"
    )


if __name__ == "__main__":
    main()
