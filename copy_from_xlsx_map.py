#!/usr/bin/env python3
"""
copy_from_xlsx_maps.py
----------------------

Copy+rename MP4 files using an XLSX table as source of truth.

XLSX requirements:
  - Column 1: human-readable title
  - Column 7: destination filename (new_filename)

Source filenames are parsed to extract a comparable title.

Usage:
  python copy_from_xlsx_titles.py table.xlsx /path/src /path/dst [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Dict

import pandas as pd


# ----------------------------------------------------------------------
# Normalization (same logic as before)
# ----------------------------------------------------------------------

def normalize(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.replace("\u00df", "ss")
    s = s.replace("_", " ")
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if c.isalnum() or c.isspace())
    return re.sub(r"\s+", " ", s).strip()


def extract_title_from_source_filename(path: Path) -> str:
    """
    Eisenbahn-Romantik-Balkan-Nostalgie-Express_Teil_1-1412345454.mp4
      -> Balkan-Nostalgie-Express Teil 1
    """
    name = path.stem
    name = re.sub(r"^Eisenbahn[- ]?Romantik[- ]*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"-\d{6,}$", "", name)
    name = name.replace("_", " ")
    return name.strip()


# ----------------------------------------------------------------------
# Build mapping from XLSX
# ----------------------------------------------------------------------

def build_title_mapping(xlsx: Path) -> Dict[str, str]:
    """
    Returns:
      normalized_title -> destination_filename
    """
    df = pd.read_excel(xlsx)

    if df.shape[1] < 7:
        raise ValueError("XLSX must have at least 7 columns")

    title_col = df.iloc[:, 0]
    dest_col = df.iloc[:, 6]

    mapping: Dict[str, str] = {}

    for i in range(len(df)):
        title = title_col.iloc[i]
        dest = dest_col.iloc[i]

        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(dest, str) or not dest.strip():
            continue

        key = normalize(title)
        if key in mapping and mapping[key] != dest:
            print(
                f"WARNING: Duplicate title in XLSX after normalization: '{title}'"
            )
            continue

        mapping[key] = dest.strip()

    return mapping


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx_table")
    ap.add_argument("source_dir")
    ap.add_argument("dest_dir")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    xlsx = Path(args.xlsx_table).resolve()
    src_dir = Path(args.source_dir).resolve()
    dst_dir = Path(args.dest_dir).resolve()

    if not xlsx.exists():
        raise SystemExit(f"ERROR: XLSX not found: {xlsx}")
    if not src_dir.is_dir():
        raise SystemExit(f"ERROR: source_dir is not a directory: {src_dir}")

    dst_dir.mkdir(parents=True, exist_ok=True)

    mapping = build_title_mapping(xlsx)
    print(f"Loaded {len(mapping)} title mappings from XLSX")

    mp4_files = sorted(src_dir.glob("*.mp4"))
    if not mp4_files:
        print("WARNING: No .mp4 files found")
        return

    copied = skipped_existing = skipped_unmapped = 0

    for src in mp4_files:
        extracted_title = extract_title_from_source_filename(src)
        key = normalize(extracted_title)

        if key not in mapping:
            print(f"WARNING: No mapping for title: {extracted_title}")
            skipped_unmapped += 1
            continue

        dst_name = mapping[key]
        dst_path = dst_dir / dst_name

        if dst_path.exists():
            print(f"WARNING: Target already exists: {dst_name}")
            skipped_existing += 1
            continue

        if args.dry_run:
            print(f"SUCCESS: DRY-RUN would copy: {src.name} -> {dst_name}")
        else:
            shutil.copy2(src, dst_path)
            print(f"SUCCESS: Copied: {src.name} -> {dst_name}")

        copied += 1

    print(
        f"\nDone. Copied={copied}, "
        f"SkippedExisting={skipped_existing}, "
        f"Unmapped={skipped_unmapped}"
    )


if __name__ == "__main__":
    main()
