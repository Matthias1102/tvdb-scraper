#! /usr/bin/env python3

from pathlib import Path
import ast
import re
import pandas as pd
from rename_er_episodes import load_episodes, find_best_match, build_new_filename, JSON_FILE

# -------- configuration --------
INPUT_FILE = "MediathekView-Filmliste-Eisenbahn-Romantik.txt"
MIN_DURATION = "00:25:00"
MIN_CONFIDENCE = 0.50          # same threshold used by copy_er_episodes.py
SORT_DESCENDING = True         # True = longest duration first
OUTPUT_CSV = "MediathekView-Filmliste-Eisenbahn-Romantik_with_TVDB_matches.csv"
OUTPUT_XLSX = "MediathekView-Filmliste-Eisenbahn-Romantik_with_TVDB_matches.xlsx"
# --------------------------------


def parse_duration_to_seconds(t: str) -> int:
    """Convert HH:MM:SS to total seconds."""
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def extract_episode_number(text: str):
    """
    Extract episode number from strings like:
      "(Folge 107)" or "Folge 107"
    Returns an int or <NA>.
    """
    if not isinstance(text, str):
        return pd.NA
    m = re.search(r"\bFolge\s*(\d+)\b", text)
    return int(m.group(1)) if m else pd.NA


def parse_input_rows(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue

            if line.endswith(","):
                line = line[:-1]

            _, value = line.split(":", 1)
            value = value.strip()

            try:
                record = ast.literal_eval(value)
            except Exception:
                continue

            rows.append(record)
    return rows


def main():
    # Load TVDB episodes once
    episodes = load_episodes(JSON_FILE)

    rows = parse_input_rows(INPUT_FILE)
    df = pd.DataFrame(rows)

    # Ensure we have at least indices: 2(title), 3(date), 4(start), 5(duration), 7(description)
    df = df[df.apply(lambda r: len(r) >= 8, axis=1)].reset_index(drop=True)

    # Duration filtering
    df["duration_seconds"] = df[5].apply(parse_duration_to_seconds)
    min_seconds = parse_duration_to_seconds(MIN_DURATION)
    df = df[df["duration_seconds"] >= min_seconds].copy()

    # Episode number (if present in description)
    df["episode"] = df[7].apply(extract_episode_number).astype("Int64")

    # Keep only columns 3,4,5,6 (human) => indices 2,3,4,5
    df_out = df[[2, 3, 4, 5, "episode", "duration_seconds"]].copy()
    df_out.columns = ["title", "date", "start_time", "duration", "episode", "duration_seconds"]

    # Match against TVDB titles and build new filenames + confidence scores
    def match_row(title: str):
        best_ep, score = find_best_match(title, episodes)
        if not best_ep:
            return pd.Series({"confidence": 0.0, "new_filename": pd.NA})
        if score < MIN_CONFIDENCE:
            return pd.Series({"confidence": float(score), "new_filename": pd.NA})
        return pd.Series({"confidence": float(score), "new_filename": build_new_filename(best_ep)})

    matches = df_out["title"].astype(str).apply(match_row)
    df_out = pd.concat([df_out, matches], axis=1)

    # sort by broadcast date
    df_out["date"] = pd.to_datetime(df_out["date"], format="%d.%m.%Y", errors="coerce")
    df_out = df_out.sort_values("date", ascending=False).reset_index(drop=True)

    # Drop helper column
    df_out = df_out.drop(columns=["duration_seconds"])

    print(f"Remaining rows (duration >= {MIN_DURATION}): {len(df_out)}")
    print(f"Rows with filename (confidence >= {MIN_CONFIDENCE}): {df_out['new_filename'].notna().sum()}")
    print(df_out.head(15).to_string(index=False))

    df_out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"Wrote: {OUTPUT_CSV}")

    df_out.to_excel(OUTPUT_XLSX, index=False)
    print(f"Wrote: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
