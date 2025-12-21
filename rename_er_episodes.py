#! /usr/bin/env python3

"""
rename_er_episodes.py
---------------------

This script copies downloaded Eisenbahn-Romantik video files (*.mp4) from a
source folder to a destination folder, naming the copied files based on
official episode information exported from TheTVDB.

Usage:
    python rename_er_episodes.py <source_folder> <destination_folder>

Notes:
  • Non-matching or low-confidence matches (score < 0.50) are skipped.
  • No files are overwritten; existing target filenames are preserved.
"""

import os
import sys
import glob
import shutil

from er_matching import (
    load_episodes,
    extract_raw_title_from_filename,
    find_best_match,
    build_new_filename,
)

TVDB_JSON_FILE = "eisenbahn_romantik_tvdb_episodes_and_specials.json"


def main():
    if len(sys.argv) != 3:
        print("Usage: python rename_er_episodes.py <source_folder> <destination_folder>")
        sys.exit(1)

    source_folder = os.path.abspath(sys.argv[1])
    destination_folder = os.path.abspath(sys.argv[2])

    print(f"Source folder:      {source_folder}")
    print(f"Destination folder: {destination_folder}")

    if not os.path.isdir(source_folder):
        print(f"ERROR: source_folder does not exist or is not a directory: {source_folder}")
        sys.exit(1)

    os.makedirs(destination_folder, exist_ok=True)

    if not os.path.exists(TVDB_JSON_FILE):
        print(f"ERROR: JSON file missing: {TVDB_JSON_FILE}")
        sys.exit(1)

    episodes = load_episodes(TVDB_JSON_FILE)

    mp4_files = glob.glob(os.path.join(source_folder, "*.mp4"))
    if not mp4_files:
        print("No .mp4 files found in source folder.")
        return

    print(f"Found {len(mp4_files)} .mp4 files")

    copied = 0
    skipped = 0

    for src_path in mp4_files:
        raw_title = extract_raw_title_from_filename(src_path)
        best_ep, score = find_best_match(raw_title, episodes)

        print(f"\nFile: {src_path}")
        print(f"  Extracted title: {raw_title}")

        if not best_ep:
            print("  No episode match found, skipping.")
            skipped += 1
            continue

        print(f"  Best match: {best_ep['title']} (score {score:.3f})")

        if score < 0.50:
            print("  Match score < 0.50 — skipping to avoid errors.")
            skipped += 1
            continue

        new_name = build_new_filename(best_ep)
        dst_path = os.path.join(destination_folder, new_name)

        if os.path.exists(dst_path):
            print(f"  Target already exists: {dst_path} — skipping.")
            skipped += 1
            continue

        print(f"  Copying to: {dst_path}")
        shutil.copy2(src_path, dst_path)
        copied += 1

    print(f"\nDone. Copied: {copied}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
