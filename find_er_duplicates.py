#!/usr/bin/env python3
"""
find_er_duplicates.py
---------------------

Scan one or more directories for Eisenbahn-Romantik episode files, parse their
filenames into structured metadata, and report duplicates.

Expected filename format:
  Eisenbahn-Romantik <episode number> - <broadcast date> - <abs episode number> - <title>.mp4

Duplicates are detected if multiple files share:
  - the same episode number
  - the same broadcast date
  - the same absolute episode number

Additionally:
  - Files that do not match the expected filename pattern are listed explicitly.
  - All reported files include their file size.

Usage:
  python find_er_duplicates.py DIR [DIR ...]
  python find_er_duplicates.py DIR --recursive --csv out.csv
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


FILENAME_RE = re.compile(
    r"""^Eisenbahn-Romantik\s+
        (?P<episode_code>S\d{2,4}E\d{1,3})\s*-\s*
        (?P<broadcast_date>\d{4}-\d{2}-\d{2})\s*-\s*
        (?P<abs_episode>\d+)\s*-\s*
        (?P<title>.+)
        \.mp4$
    """,
    re.VERBOSE,
)


def size_mib(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def scan_files(dirs: List[Path], recursive: bool) -> List[Path]:
    files: List[Path] = []
    for d in dirs:
        if recursive:
            files.extend(p for p in d.rglob("*.mp4") if p.is_file())
        else:
            files.extend(p for p in d.glob("*.mp4") if p.is_file())
    return files


def parse_filename(p: Path) -> Optional[Dict[str, object]]:
    m = FILENAME_RE.match(p.name)
    if not m:
        return None

    gd = m.groupdict()
    return {
        "directory": str(p.parent),
        "filename": p.name,
        "path": str(p),
        "size_mib": round(size_mib(p), 2),
        "episode_code": gd["episode_code"].upper(),
        "broadcast_date": gd["broadcast_date"],
        "abs_episode": int(gd["abs_episode"]),
        "title": gd["title"],
    }


def print_duplicates(df: pd.DataFrame, key: str) -> None:
    dup_df = df[df.duplicated(subset=[key], keep=False)].sort_values([key, "path"])
    if dup_df.empty:
        print(f"✅ No duplicates by {key}.")
        return

    print(f"\n⚠️  Duplicates by {key} ({dup_df[key].nunique()} duplicate keys):")
    for value, group in dup_df.groupby(key, sort=True):
        print(f"\n  {key} = {value}  ({len(group)} files)")
        for _, r in group.iterrows():
            print(f"    - {r['path']}  ({r['size_mib']:.2f} MiB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", help="One or more directories to scan")
    ap.add_argument("--recursive", action="store_true", help="Scan subdirectories")
    ap.add_argument("--csv", help="Optional CSV output of parsed files")
    args = ap.parse_args()

    dirs = [Path(d).expanduser().resolve() for d in args.dirs]
    for d in dirs:
        if not d.is_dir():
            raise SystemExit(f"ERROR: Not a directory: {d}")

    files = scan_files(dirs, recursive=args.recursive)
    if not files:
        print("No .mp4 files found.")
        return

    parsed: List[Dict[str, object]] = []
    skipped: List[Path] = []

    for p in files:
        row = parse_filename(p)
        if row is None:
            skipped.append(p)
        else:
            parsed.append(row)

    print(f"Scanned: {len(files)} files")
    print(f"Parsed:  {len(parsed)} files")
    print(f"Skipped (pattern mismatch): {len(skipped)} files")

    if not parsed:
        print("No files matched the expected filename pattern.")
        return

    df = pd.DataFrame(parsed)

    # Report duplicates
    print_duplicates(df, "episode_code")
    print_duplicates(df, "broadcast_date")
    print_duplicates(df, "abs_episode")

    # List skipped files
    if skipped:
        print("\n⚠️  Skipped files (pattern mismatch):")
        for p in sorted(skipped):
            print(f"  - {p}  ({size_mib(p):.2f} MiB)")

    # Optional CSV output
    if args.csv:
        out = Path(args.csv).expanduser().resolve()
        df.sort_values(
            ["episode_code", "broadcast_date", "abs_episode", "path"]
        ).to_csv(out, index=False, encoding="utf-8")
        print(f"\nWrote CSV: {out}")


if __name__ == "__main__":
    main()
