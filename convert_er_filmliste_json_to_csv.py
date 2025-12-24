#!/usr/bin/env python3
"""
convert_er_filmliste_json_to_csv.py
----------------------------------

Convert an extracted Eisenbahn-Romantik MediathekView JSON file (list of film
records) into a CSV file with columns:

  title,date,start_time,duration,episode

ONLY episodes WITH an episode number ("Folge <n>") are kept.

Deduplication:
  - canonical key = (episode number + normalized title)
  - keep the most recent broadcast
  - tie-breakers: longer duration, later start_time

Usage:
  python convert_er_filmliste_json_to_csv.py input.json output.csv
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import List

import pandas as pd


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def extract_episode_number(description: str):
    """Extract episode number from '(Folge 107)' or 'Folge 107'."""
    if not isinstance(description, str):
        return pd.NA
    m = re.search(r"\bFolge\s*(\d+)\b", description)
    return int(m.group(1)) if m else pd.NA


def parse_duration_to_seconds(t: str) -> int:
    """Convert HH:MM:SS -> seconds. Returns 0 on failure."""
    if not isinstance(t, str):
        return 0
    try:
        h, m, s = map(int, t.split(":"))
        return h * 3600 + m * 60 + s
    except Exception:
        return 0


def normalize_title(title: str) -> str:
    """
    Normalize title for deduplication:
      - lowercase
      - remove accents
      - remove punctuation
      - remove 'eisenbahn romantik'
      - collapse whitespace
    """
    if not isinstance(title, str):
        return ""

    s = title.lower()
    s = s.replace("–", "-").replace("—", "-")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if c.isalnum() or c.isspace())
    s = re.sub(r"\beisenbahn\s*romantik\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ----------------------------------------------------------------------
# JSON → reduced DataFrame
# ----------------------------------------------------------------------

def json_to_reduced_df(records: List[list]) -> pd.DataFrame:
    """
    Build a DataFrame with ONLY:
      title, date, start_time, duration, episode

    Expected MediathekView indices:
      2 -> title
      3 -> date (DD.MM.YYYY)
      4 -> start_time (HH:MM[:SS])
      5 -> duration (HH:MM:SS)
      7 -> description
    """
    rows = []
    for rec in records:
        if not isinstance(rec, list) or len(rec) < 8:
            continue

        episode = extract_episode_number(rec[7])
        if pd.isna(episode):
            continue  # 🚨 FILTER: only episodes with number

        rows.append(
            {
                "title": rec[2],
                "date": rec[3],
                "start_time": rec[4],
                "duration": rec[5],
                "episode": episode,
            }
        )

    df = pd.DataFrame(
        rows, columns=["title", "date", "start_time", "duration", "episode"]
    )
    if not df.empty:
        df["episode"] = df["episode"].astype("Int64")
    return df


# ----------------------------------------------------------------------
# Deduplication
# ----------------------------------------------------------------------

def dedupe_final(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate rows by:
      (episode number + normalized title),
    keeping the most recent broadcast.
    """
    if df.empty:
        return df

    df = df.copy()

    df["_title_norm"] = df["title"].apply(normalize_title)
    df["_date_dt"] = pd.to_datetime(df["date"], format="%d.%m.%Y", errors="coerce")
    df["_dur_s"] = df["duration"].apply(parse_duration_to_seconds)
    df["_start_norm"] = df["start_time"].astype(str).str.strip()

    df = df.sort_values(
        by=["episode", "_title_norm", "_date_dt", "_dur_s", "_start_norm"],
        ascending=[True, True, False, False, False],
        kind="mergesort",
    )

    df = df.drop_duplicates(
        subset=["episode", "_title_norm"],
        keep="first",
    )

    df = df.drop(columns=["_title_norm", "_date_dt", "_dur_s", "_start_norm"])

    # Nice ordering
    df["_date_dt"] = pd.to_datetime(df["date"], format="%d.%m.%Y", errors="coerce")
    df = (
        df.sort_values("_date_dt", ascending=False, kind="mergesort")
          .drop(columns=["_date_dt"])
          .reset_index(drop=True)
    )

    return df


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    if len(sys.argv) != 3:
        print("Usage: python convert_er_filmliste_json_to_csv.py <input.json> <output.csv>")
        sys.exit(1)

    in_json = Path(sys.argv[1]).expanduser().resolve()
    out_csv = Path(sys.argv[2]).expanduser().resolve()

    if not in_json.exists():
        sys.exit(f"ERROR: Input JSON not found: {in_json}")

    with in_json.open("r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        sys.exit("ERROR: Input JSON must contain a list of records")

    df = json_to_reduced_df(records)
    before = len(df)

    df = dedupe_final(df)
    after = len(df)

    df.to_csv(out_csv, index=False, encoding="utf-8")

    print(f"Loaded records:       {len(records)}")
    print(f"Episodes extracted:  {before}")
    print(f"After deduplication: {after}")
    print(f"Wrote:               {out_csv}")


if __name__ == "__main__":
    main()
