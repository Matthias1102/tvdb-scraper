#!/usr/bin/env python3
"""
mark_existing_files.py
----------------------

Reads an XLSX table (e.g. produced by parse_tvdb_film_list.py and manually edited),
checks whether each row's `new_filename` already exists in a target folder, and
adds a new column indicating existence.

Matching strategy:
  1) Exact filename match in folder
  2) "Similar" match: any file in folder containing same season/episode code (S..E..)

Outputs a new XLSX file with added columns:
  - file_exists (bool)
  - match_type ("exact", "by_episode_code", "")

Usage:
  python mark_existing_files.py input.xlsx /path/to/folder [output.xlsx]

Notes:
  - Requires pandas + openpyxl installed.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


EP_CODE_RE = re.compile(r"(S\d{2,4}E\d{1,3})", re.IGNORECASE)


def extract_episode_code(filename: str) -> Optional[str]:
    if not isinstance(filename, str):
        return None
    m = EP_CODE_RE.search(filename)
    return m.group(1).upper() if m else None


def build_folder_index(folder: Path):
    """
    Build an index of existing files:
      - exact filenames set
      - mapping episode_code -> any matching filename (first match)
    """
    exact = set()
    by_code = {}

    for p in folder.iterdir():
        if not p.is_file():
            continue
        exact.add(p.name)

        code = extract_episode_code(p.name)
        if code and code not in by_code:
            by_code[code] = p.name

    return exact, by_code


def check_existence(new_filename: str, exact_set, by_code_map) -> Tuple[bool, str]:
    """
    Returns (exists, match_type)
    match_type: "exact", "by_episode_code", ""
    """
    if not isinstance(new_filename, str) or not new_filename.strip():
        return False, ""

    name = new_filename.strip()

    if name in exact_set:
        return True, "exact"

    code = extract_episode_code(name)
    if code and code in by_code_map:
        return True, "by_episode_code"

    return False, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_xlsx", help="Edited XLSX input file")
    ap.add_argument("folder", help="Folder to check for existing files")
    ap.add_argument("output_xlsx", nargs="?", default=None, help="Output XLSX (optional)")
    args = ap.parse_args()

    input_xlsx = Path(args.input_xlsx).expanduser().resolve()
    folder = Path(args.folder).expanduser().resolve()

    if not input_xlsx.exists():
        raise SystemExit(f"ERROR: Input XLSX not found: {input_xlsx}")
    if not folder.is_dir():
        raise SystemExit(f"ERROR: Folder is not a directory: {folder}")

    output_xlsx = (
        Path(args.output_xlsx).expanduser().resolve()
        if args.output_xlsx
        else input_xlsx.with_name(input_xlsx.stem + "_with_exists.xlsx")
    )

    df = pd.read_excel(input_xlsx)

    if "new_filename" not in df.columns:
        raise SystemExit(
            "ERROR: Column 'new_filename' not found in the XLSX. "
            f"Columns are: {list(df.columns)}"
        )

    exact_set, by_code_map = build_folder_index(folder)

    # Apply row-wise checks
    results = df["new_filename"].apply(lambda s: check_existence(s, exact_set, by_code_map))
    df["file_exists"] = results.apply(lambda t: bool(t[0]))
    df["match_type"] = results.apply(lambda t: t[1])

    # Write output
    df.to_excel(output_xlsx, index=False)
    print(f"Wrote: {output_xlsx}")
    print(f"Rows with file_exists=True: {int(df['file_exists'].sum())} / {len(df)}")


if __name__ == "__main__":
    main()
