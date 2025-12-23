#!/usr/bin/env python3
"""
check_er_csv_against_filesystem.py
---------------------------------

Check whether Eisenbahn-Romantik episodes listed in a CSV file exist as .mp4
files in a given directory.

Expected CSV columns (TVDB export):
  SeasonEpisode,Date,AbsEpisode,Title

(Some older variants may use "BroadcastDate" instead of "Date". This script
supports both.)

Expected filename pattern (prefix match):
  Eisenbahn-Romantik <SeasonEpisode> - <Date> - <AbsEpisode> - <title>.mp4

The script:
  - builds an expected filename prefix from each CSV row
  - checks if any .mp4 file in the directory starts with that prefix
  - reports existence and matched filename

Usage:
  python check_er_csv_against_filesystem.py episodes.csv /path/to/mp4_dir
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def pick_date_column(df: pd.DataFrame) -> str:
    if "Date" in df.columns:
        return "Date"
    if "BroadcastDate" in df.columns:
        return "BroadcastDate"
    raise ValueError("CSV must contain a 'Date' column (or 'BroadcastDate').")


def build_expected_prefix(row: pd.Series, date_col: str) -> str:
    """
    Build the deterministic filename prefix used for matching.
    """
    return (
        f"Eisenbahn-Romantik {row['SeasonEpisode']} - "
        f"{row[date_col]} - "
        f"{row['AbsEpisode']}"
    )


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: python check_er_csv_against_filesystem.py "
            "<episodes.csv> <mp4_directory>"
        )
        sys.exit(1)

    csv_path = Path(sys.argv[1]).expanduser().resolve()
    mp4_dir = Path(sys.argv[2]).expanduser().resolve()

    if not csv_path.exists():
        sys.exit(f"ERROR: CSV file not found: {csv_path}")
    if not mp4_dir.is_dir():
        sys.exit(f"ERROR: Not a directory: {mp4_dir}")

    df = pd.read_csv(csv_path)

    required_cols = {"SeasonEpisode", "AbsEpisode", "Title"}
    missing = required_cols - set(df.columns)
    if missing:
        sys.exit(f"ERROR: CSV missing required columns: {sorted(missing)}")

    try:
        date_col = pick_date_column(df)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")

    # Collect all mp4 filenames once
    mp4_files = [p.name for p in mp4_dir.glob("*.mp4")]

    file_exists = []
    matched_filename = []

    for _, row in df.iterrows():
        prefix = build_expected_prefix(row, date_col)
        matches = [f for f in mp4_files if f.startswith(prefix)]

        if matches:
            file_exists.append(True)
            matched_filename.append(matches[0])
        else:
            file_exists.append(False)
            matched_filename.append("")

    df["file_exists"] = file_exists
    df["matched_filename"] = matched_filename

    out_csv = csv_path.with_name(csv_path.stem + "_with_filesystem_check.csv")
    df.to_csv(out_csv, index=False, encoding="utf-8")

    found = int(df["file_exists"].sum())
    missing_n = int((~df["file_exists"]).sum())

    print(f"Checked episodes: {len(df)}")
    print(f"Files found:      {found}")
    print(f"Files missing:    {missing_n}")
    print(f"Wrote: {out_csv}")


if __name__ == "__main__":
    main()
