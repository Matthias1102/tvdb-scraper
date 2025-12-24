#!/usr/bin/env python3
"""
report_missing_er_files.py
--------------------------

Report ONLY missing Eisenbahn-Romantik episodes based on a MediathekView-derived CSV,
and generate expected filenames using TVDB metadata.

Inputs:
  1) MediathekView CSV (columns: title,date,start_time,duration,episode)
     - episode is treated as the absolute episode number (Folge <n>)
  2) Folder containing renamed .mp4 files
  3) TVDB JSON (e.g. eisenbahn_romantik_tvdb_with_specials.json)
     - list of dicts with at least:
         abs_episode, season_episode_code, air_date_iso, title

Presence check:
  - Parse abs episode numbers from filenames using robust patterns.
  - Supports abs tokens like "890", "890XL", "890XS" etc.: the leading digits
    are used as abs_episode (e.g. "890XL" -> 890).

Output:
  <mediaview_stem>_missing.csv

Usage:
  python report_missing_er_files.py MediathekView.csv /path/to/mp4_folder tvdb.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd


def sanitize_for_filename(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.replace("/", "-").replace("\\", "-")
    s = re.sub(r'[:*?"<>|]', "", s)
    return s.strip()


# Primary: match intended naming scheme, allow abs token with suffix (e.g., 890XL)
# Tolerates unicode dashes and the broken "89- " variant.
FILENAME_MAIN_RE = re.compile(
    r"""^Eisenbahn-Romantik\s+
        (?P<se_code>S\d{2,4}E\d{1,3})\s*[-–—]\s*
        (?P<date>\d{4}-\d{2}-\d{2})\s*[-–—]\s*
        (?P<abs_token>\d+[A-Za-z]{0,8})\s*(?:[-–—]\s*|-\s*)   # " - " or "89- "
        (?P<title>.+)\.mp4$
    """,
    re.VERBOSE,
)

# Fallback: find "... <date> - <absToken> -/–/—/-(broken)"
FILENAME_FALLBACK_ABS_RE = re.compile(
    r"""\b\d{4}-\d{2}-\d{2}\b\s*[-–—]\s*(\d+[A-Za-z]{0,8})\s*(?:[-–—]|-)""",
    re.VERBOSE,
)

LEADING_DIGITS_RE = re.compile(r"^(\d+)")


def load_tvdb_index(tvdb_json_path: Path) -> Dict[int, dict]:
    data = json.loads(tvdb_json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("TVDB JSON must contain a list of episode dicts.")

    idx: Dict[int, dict] = {}
    for ep in data:
        if not isinstance(ep, dict):
            continue
        abs_ep = ep.get("abs_episode")
        if abs_ep is None:
            continue
        try:
            abs_i = int(abs_ep)
        except (TypeError, ValueError):
            continue
        idx.setdefault(abs_i, ep)
    return idx


def build_expected_filename(tvdb_ep: dict) -> str:
    season_code = tvdb_ep.get("season_episode_code") or "S00E00"
    date_iso = tvdb_ep.get("air_date_iso") or "0000-00-00"
    abs_ep = tvdb_ep.get("abs_episode")
    title = sanitize_for_filename(tvdb_ep.get("title") or "Unknown Title")
    return f"Eisenbahn-Romantik {season_code} - {date_iso} - {abs_ep} - {title}.mp4"


def abs_from_token(token: str) -> Optional[int]:
    """
    Convert an abs token like '890XL' -> 890.
    Returns None if no leading digits.
    """
    if not isinstance(token, str):
        return None
    m = LEADING_DIGITS_RE.match(token.strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def extract_abs_from_filename(name: str) -> Optional[int]:
    """
    Try to extract abs episode number from a filename.
    Supports tokens like 890XL / 890XS by using leading digits.
    Returns int(abs) or None.
    """
    m = FILENAME_MAIN_RE.match(name)
    if m:
        return abs_from_token(m.group("abs_token"))

    m2 = FILENAME_FALLBACK_ABS_RE.search(name)
    if m2:
        return abs_from_token(m2.group(1))

    return None


def build_abs_index(folder: Path) -> Tuple[Set[int], List[str]]:
    """
    Return:
      - set of abs episodes present in folder (digit-part only)
      - list of filenames that could not be parsed (diagnostics)
    """
    present_abs: Set[int] = set()
    unparsed: List[str] = []

    for p in folder.glob("*.mp4"):
        abs_ep = extract_abs_from_filename(p.name)
        if abs_ep is None:
            unparsed.append(p.name)
        else:
            present_abs.add(abs_ep)

    return present_abs, unparsed


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python report_missing_er_files.py <mediaview.csv> <mp4_folder> <tvdb.json>")
        sys.exit(1)

    mv_csv = Path(sys.argv[1]).expanduser().resolve()
    folder = Path(sys.argv[2]).expanduser().resolve()
    tvdb_json = Path(sys.argv[3]).expanduser().resolve()

    if not mv_csv.exists():
        sys.exit(f"ERROR: MediathekView CSV not found: {mv_csv}")
    if not folder.is_dir():
        sys.exit(f"ERROR: Not a directory: {folder}")
    if not tvdb_json.exists():
        sys.exit(f"ERROR: TVDB JSON not found: {tvdb_json}")

    df = pd.read_csv(mv_csv, encoding="utf-8")

    required_cols = {"title", "date", "episode"}
    missing = required_cols - set(df.columns)
    if missing:
        sys.exit(f"ERROR: Missing required columns in MV CSV: {sorted(missing)}")

    df = df.copy()
    df["episode"] = pd.to_numeric(df["episode"], errors="coerce")
    df_abs = df[df["episode"].notna()].copy()
    df_abs["episode"] = df_abs["episode"].astype(int)

    if df_abs.empty:
        print("No rows with an episode number in the MediathekView CSV. Nothing to check.")
        return

    present_abs, unparsed_files = build_abs_index(folder)
    tvdb_index = load_tvdb_index(tvdb_json)

    requested_abs = sorted(set(df_abs["episode"].tolist()))
    missing_abs = [a for a in requested_abs if a not in present_abs]

    out_rows = []
    for abs_ep in missing_abs:
        mv_row = df_abs[df_abs["episode"] == abs_ep].iloc[0]
        tvdb_ep = tvdb_index.get(abs_ep)

        out_rows.append(
            {
                "abs_episode": abs_ep,
                "mv_title": mv_row.get("title", ""),
                "mv_date": mv_row.get("date", ""),
                "tvdb_season_episode": (tvdb_ep.get("season_episode_code", "") if tvdb_ep else ""),
                "tvdb_date": (tvdb_ep.get("air_date_iso", "") if tvdb_ep else ""),
                "tvdb_title": (tvdb_ep.get("title", "") if tvdb_ep else ""),
                "expected_filename": (build_expected_filename(tvdb_ep) if tvdb_ep else ""),
            }
        )

    out_df = pd.DataFrame(out_rows)
    out_csv = mv_csv.with_name(mv_csv.stem + "_missing.csv")
    out_df.to_csv(out_csv, index=False, encoding="utf-8")

    print(f"Unique abs episodes in MV CSV: {len(requested_abs)}")
    print(f"Parsed abs episodes on disk:   {len(present_abs)}")
    print(f"Missing abs episodes:          {len(missing_abs)}")
    print(f"Wrote: {out_csv}")

    if unparsed_files:
        diag = mv_csv.with_name(mv_csv.stem + "_unparsed_filenames.txt")
        diag.write_text("\n".join(sorted(unparsed_files)), encoding="utf-8")
        print(f"WARNING: {len(unparsed_files)} filenames did not match the expected pattern.")
        print(f"Wrote: {diag}")


if __name__ == "__main__":
    main()
