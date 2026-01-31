#!/usr/bin/env python3

"""
check_videos_presence.py

Purpose
-------
This script checks whether episode video files referenced in a CSV table are
present in a given directory. Presence is determined using a *stable filename
prefix* rather than the full filename, making the comparison robust against
Unicode punctuation differences, title changes, and formatting variations.

CSV Format
----------
The input CSV file must contain the following columns (in this order):

    SeasonEpisode,Date,AbsEpisode,Title,TargetFilename

A new column named `VideoPresent` is inserted **between `AbsEpisode` and `Title`**
in the output CSV.

Matching Logic
--------------
An episode video is considered *present* if **any file in the target directory**
matches the following prefix pattern:

    <SeasonEpisode> - <Date> - <AbsEpisode> - ...

Examples of matching filenames:

    Eisenbahn-Romantik S2024E10 - 2024-03-22 - 1071 - Title.mp4
    Eisenbahn-Romantik S2024E10 - 2024-03-22 - 1071 XL - Title.mp4
    S2024E10 - 2024-03-22 - 1071XL - Something else.mkv

The comparison:
- is **case-insensitive**
- ignores title text entirely
- tolerates Unicode differences (dash variants, apostrophes, non-breaking spaces)
- ignores invisible Unicode format characters (e.g. zero-width spaces)
- accepts an optional `XL` suffix after the absolute episode number

The presence of `XL` is treated as “better than regular” and therefore counts
as a valid match for the episode.

Normalization
-------------
Before comparison, both CSV-derived keys and filesystem filenames are normalized:
- Unicode NFKC normalization
- removal of invisible Unicode format characters (category Cf)
- normalization of dash and apostrophe variants
- normalization of non-breaking spaces
- collapsing of whitespace
- case folding (case-insensitive)

Directory Scanning
------------------
By default, only files directly inside the specified directory are scanned.
If `--recursive` is supplied, all subdirectories are scanned recursively.

Usage
-----
Basic usage:

    python check_videos_presence.py --csv episodes.csv --dir /path/to/videos

Recursive directory scan:

    python check_videos_presence.py --csv episodes.csv --dir /path/to/videos --recursive

Example:

    ./check_video_presence.py --csv eisenbahn_romantik_tvdb_episodes.csv \
                              --out eisenbahn_romantik_tvdb_episodes_with_presence_check.csv \
                              --dir /mnt/omv-data1/Video/Dokumentationen/Eisenbahn-Romantik

Output
------
A new CSV file is written (by default `<input>_checked.csv`) containing all
original columns plus the inserted `VideoPresent` column with values:

    True  — a matching video file was found
    False — no matching video file was found

Exit Status
-----------
- 0 on success
- non-zero if input files are missing or CSV format is invalid
"""




from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# ---------- Normalization (lightweight but robust) ----------

DASH_EQUIVALENTS = {
    "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015",
    "\u2212", "\u2043", "\u00ad",
}
DASH_TRANSLATION = {ord(ch): "-" for ch in DASH_EQUIVALENTS}

APOSTROPHE_EQUIVALENTS = {
    "\u2018", "\u2019", "\u201B", "\u2032",
    "\u00B4", "\u0060", "\u02BC", "\u02B9", "\uFF07",
}
APOSTROPHE_TRANSLATION = {ord(ch): "'" for ch in APOSTROPHE_EQUIVALENTS}

SPACE_EQUIVALENTS = {
    "\u00A0",  # NBSP
    "\u2007",  # figure space
    "\u202F",  # narrow NBSP
}
SPACE_TRANSLATION = {ord(ch): " " for ch in SPACE_EQUIVALENTS}

WS_RE = re.compile(r"\s+")


def _remove_format_chars(s: str) -> str:
    # Remove invisible Unicode format characters (category Cf), e.g. ZWSP, BOM, word joiner
    return "".join(ch for ch in s if unicodedata.category(ch) != "Cf")


def normalize(s: str) -> str:
    """
    Normalize for resilient matching:
    - NFKC normalization
    - remove invisible format chars (Cf)
    - normalize dash / apostrophe variants
    - normalize NBSP-like spaces
    - collapse whitespace
    - case-insensitive via casefold()
    """
    s = unicodedata.normalize("NFKC", s)
    s = _remove_format_chars(s)
    s = s.translate(DASH_TRANSLATION)
    s = s.translate(APOSTROPHE_TRANSLATION)
    s = s.translate(SPACE_TRANSLATION)
    s = WS_RE.sub(" ", s).strip()
    return s.casefold()


# ---------- CSV helpers ----------

def detect_dialect_and_headers(csv_path: Path, encoding: str) -> Tuple[csv.Dialect, List[str]]:
    sample_size = 64 * 1024
    with csv_path.open("r", encoding=encoding, newline="") as f:
        sample = f.read(sample_size)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(f, dialect)
        try:
            headers = next(reader)
        except StopIteration:
            raise SystemExit(f"CSV appears to be empty: {csv_path}")

    return dialect, [h.strip() for h in headers]


# ---------- Prefix extraction (XL tolerant) ----------

# Matches a stable prefix near the start of the filename:
# ... S2024E10 - 2024-03-22 - 1071 - ...
# ... S2024E10 - 2024-03-22 - 1071 XL - ...
#
# XL handling: allow optional "XL" after the digits with optional separators/spaces.
PREFIX_RE = re.compile(
    r"""
    ^\s*
    .*?                           # optional series prefix text (non-greedy)
    (?P<se>\bS\d{1,4}E\d{1,4}\b)   # SeasonEpisode like S01E01 or S2024E10
    \s*-\s*
    (?P<date>\d{4}-\d{2}-\d{2})    # yyyy-mm-dd
    \s*-\s*
    (?P<abs>\d+)                  # AbsEpisode number digits
    (?:\s*[- ]?\s*xl)?            # optional XL suffix (e.g. " XL", "XL", "-XL") - case-insensitive via re.I
    \s*-\s*
    """,
    re.VERBOSE | re.IGNORECASE,
)

ABS_DIGITS_RE = re.compile(r"\d+")


def key_from_filename(filename: str) -> Optional[str]:
    """
    Extract normalized key: "SxxxxExxxx - yyyy-mm-dd - abs - "
    from a filesystem filename. Returns None if pattern not found.
    """
    m = PREFIX_RE.match(filename)
    if not m:
        return None

    raw = f"{m.group('se')} - {m.group('date')} - {m.group('abs')} - "
    return normalize(raw)


def _abs_digits(value: str) -> str:
    """
    Extract the first run of digits from AbsEpisode; keeps the match stable even if CSV has "1071 XL".
    """
    value = (value or "").strip()
    m = ABS_DIGITS_RE.search(value)
    return m.group(0) if m else ""


def key_from_row(row: Dict[str, str]) -> str:
    """
    Build normalized key from CSV row:
    "{SeasonEpisode} - {Date} - {AbsEpisodeDigits} - "
    """
    se = (row.get("SeasonEpisode") or "").strip()
    date = (row.get("Date") or "").strip()
    abs_ep = _abs_digits(row.get("AbsEpisode") or "")
    raw = f"{se} - {date} - {abs_ep} - "
    return normalize(raw)


def build_key_index(directory: Path, recursive: bool) -> set[str]:
    keys: set[str] = set()
    it = directory.rglob("*") if recursive else directory.iterdir()
    for p in it:
        if not p.is_file():
            continue
        k = key_from_filename(p.name)
        if k:
            keys.add(k)
    return keys


# ---------- CLI ----------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mark CSV rows as present if a file exists with matching SeasonEpisode/Date/AbsEpisode prefix."
    )
    p.add_argument("--csv", required=True, type=Path, help="Input CSV file path")
    p.add_argument("--dir", required=True, type=Path, help="Directory containing episode video files")
    p.add_argument("--out", type=Path, default=None, help="Output CSV path (default: <input>_checked.csv)")
    p.add_argument("--recursive", action="store_true", help="Search recursively under --dir")
    p.add_argument("--encoding", default="utf-8-sig", help="CSV encoding (default: utf-8-sig)")
    p.add_argument("--present-col", default="VideoPresent", help='Inserted column name (default: "VideoPresent")')
    return p.parse_args()


# ---------- Main ----------

def main() -> int:
    args = parse_args()

    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")
    if not args.dir.is_dir():
        raise SystemExit(f"Directory not found: {args.dir}")

    out_path = args.out or args.csv.with_name(f"{args.csv.stem}_checked{args.csv.suffix}")

    dialect, headers = detect_dialect_and_headers(args.csv, args.encoding)

    expected = ["SeasonEpisode", "Date", "AbsEpisode", "Title", "TargetFilename"]
    missing = [c for c in expected if c not in headers]
    if missing:
        raise SystemExit(f"Missing required columns: {missing}\nFound headers: {headers}")

    if args.present_col in headers:
        raise SystemExit(f'Column "{args.present_col}" already exists in input CSV.')

    # Insert VideoPresent between AbsEpisode and Title
    abs_idx = headers.index("AbsEpisode")
    title_idx = headers.index("Title")
    if title_idx != abs_idx + 1:
        raise SystemExit(
            'Expected "Title" to be immediately after "AbsEpisode" '
            "to insert the new column between them."
        )
    out_headers = headers[: abs_idx + 1] + [args.present_col] + headers[abs_idx + 1 :]

    key_index = build_key_index(args.dir, recursive=args.recursive)

    total = present = 0

    with args.csv.open("r", encoding=args.encoding, newline="") as fin, out_path.open(
        "w", encoding=args.encoding, newline=""
    ) as fout:
        reader = csv.DictReader(fin, dialect=dialect)
        writer = csv.DictWriter(fout, fieldnames=out_headers, dialect=dialect)
        writer.writeheader()

        for row in reader:
            k = key_from_row(row)
            is_present = bool(k) and (k in key_index)

            new_row: Dict[str, str] = {}
            for h in headers:
                new_row[h] = row.get(h, "")
                if h == "AbsEpisode":
                    new_row[args.present_col] = "True" if is_present else "False"

            writer.writerow(new_row)

            total += 1
            if is_present:
                present += 1

    print(f"Rows processed: {total}")
    print(f"Present: {present} / {total}")
    print(f"Output written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
