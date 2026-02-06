#! /usr/bin/env python3

"""
fetch-railway-romance-episodes.py
---------------------------------

This script downloads a complete episode list for the TV series
"Eisenbahn-Romantik" from TheTVDB's public "All Seasons" page:

    https://thetvdb.com/series/railway-romance/allseasons/official

It extracts:
  • season/episode codes (SyyyyEnn format)
  • air dates (converted to YYYY-MM-DD)
  • absolute episode numbers (sequential 1..N)
  • titles (as provided by TheTVDB)
  • a suggested target filename for each episode

Two output files are generated in the script directory:
    eisenbahn_romantik_tvdb_episodes.csv
    eisenbahn_romantik_tvdb_episodes.json

CSV format:
    SeasonEpisode,Date,AbsEpisode,Title,TargetFilename

JSON format:
    A list of dictionaries with fields:
        season_episode_code
        season_raw
        ep_in_season
        title
        air_date_iso
        abs_episode
        target_filename

Usage:
    python fetch-railway-romance-episodes.py

Notes:
  • This script does *not* rely on TheTVDB’s API, only on the public HTML pages.
  • Absolute episode numbers are assigned after sorting by season and episode.
  • If TheTVDB changes its HTML layout, the scraper may need adjustments.
"""

import csv
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from html import unescape
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

ALLSEASONS_URL = "https://thetvdb.com/series/railway-romance/allseasons/official"
BASE_URL = "https://thetvdb.com"


def sanitize_filename_component(s: str) -> str:
    """
    Make a string safe-ish for filenames across common filesystems.

    - Replaces / and \\ with '-'
    - Replaces common forbidden characters on Windows: <>:"|?* with ''
    - Collapses whitespace
    - Strips trailing dots/spaces
    """
    s = s.replace("/", "-").replace("\\", "-")
    s = re.sub(r'[<>:"|?*]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(" .")
    return s


def build_target_filename(ep: "Episode") -> str:
    """
    Eisenbahn-Romantik <season_episode_code> - <air_date_iso> - <abs_episode> - <title>.mp4
    Missing values are left blank (but separators remain stable).
    """
    abs_str = str(ep.abs_episode) if ep.abs_episode is not None else ""
    title = sanitize_filename_component(ep.title)
    return f"Eisenbahn-Romantik {ep.season_episode_code} - {ep.air_date_iso} - {abs_str} - {title}.mp4"


@dataclass
class Episode:
    season_episode_code: str  # SyyyyEnn (yyyy = year, or 0000 for specials)
    season_raw: int           # Season number from TheTVDB (0 = specials, 1991 = year etc.)
    ep_in_season: int         # Episode number within that season
    title: str
    air_date_iso: str         # yyyy-mm-dd or "" (if missing on TheTVDB)
    abs_episode: Optional[int] = None  # will be filled later as 1..N
    target_filename: str = ""          # will be filled later


def parse_date_en(date_str: str) -> str:
    """
    Parse an English date like 'April 7, 1991' -> '1991-04-07'.
    Returns '' if the date cannot be parsed.
    """
    date_str = date_str.strip()
    if not date_str:
        return ""

    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return ""


def fetch_all_episodes_from_allseasons() -> List[Episode]:
    """
    Fetch episodes from TheTVDB "All Seasons" page:

      - Normal episodes: S1991E01, S1992E05, ...
      - Specials (season 0): S0E1, S0E12, ...

    For each episode we extract:
      - SeasonEpisode code (SyyyyEnn, yyyy=0000 for season 0)
      - Title
      - Air date (if present)
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ER-TVDB-Scraper/2.0; +https://example.com/)"
        )
    }

    print(f"Loading All-Seasons page: {ALLSEASONS_URL}")
    resp = requests.get(ALLSEASONS_URL, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Cache age diagnostics
    age_header = resp.headers.get("Age")
    if age_header is not None:
        try:
            age_seconds = int(age_header)
            hours = age_seconds // 3600
            minutes = (age_seconds % 3600) // 60
            seconds = age_seconds % 60
            print(
                f"CDN cache age: {age_seconds} s "
                f"({hours} h {minutes} min {seconds} s)"
            )
        except ValueError:
            print(f"CDN cache age header present but not numeric: {age_header}")
    else:
        print("No Age header present (likely not served from CDN cache).")

    # Also show cache status
    x_cache = resp.headers.get("X-Cache")
    if x_cache:
        print(f"CDN cache status: {x_cache}")


    # All episode links on the All Seasons page
    episode_links = soup.select('a[href*="/series/railway-romance/episodes/"]')

    episodes: List[Episode] = []
    seen_urls = set()

    for a in episode_links:
        href = a.get("href")
        if not href:
            continue

        url = href if href.startswith("http") else BASE_URL + href
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Use parent <li> as context; it contains code, title, date, etc.
        li = a.find_parent("li")
        if li is None:
            parent = a.parent
            text_block = (
                parent.get_text(" ", strip=True) if parent else a.get_text(" ", strip=True)
            )
        else:
            text_block = li.get_text(" ", strip=True)

        # Match S<season>E<episode>, e.g. S1991E01, S0E1
        m = re.search(r"S(\d{1,4})E(\d{1,3})", text_block)
        if not m:
            continue

        season_raw = int(m.group(1))          # e.g. 1991 or 0
        ep_in_season = int(m.group(2))        # e.g. 1

        # SeasonEpisode code with 4-digit season (0000 for specials)
        season_episode_code = f"S{season_raw:04d}E{ep_in_season:02d}"

        # Extract English date from the text (e.g. "April 7, 1991")
        date_match = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})", text_block)
        air_date_iso = parse_date_en(date_match.group(1)) if date_match else ""

        title = unescape(a.get_text(" ", strip=True))

        episodes.append(
            Episode(
                season_episode_code=season_episode_code,
                season_raw=season_raw,
                ep_in_season=ep_in_season,
                title=title,
                air_date_iso=air_date_iso,
            )
        )

    # Sort in the order TheTVDB uses: season, then episode-in-season
    episodes.sort(key=lambda e: (e.season_raw, e.ep_in_season))
    print(f"Found {len(episodes)} episodes (including specials).")
    return episodes


def assign_absolute_numbers_and_filenames(episodes: List[Episode]) -> None:
    """
    Assign absolute episode numbers 1..N in the listing order, and build target filenames.
    """
    for idx, ep in enumerate(episodes, start=1):
        ep.abs_episode = idx
        ep.target_filename = build_target_filename(ep)


def write_csv(episodes: List[Episode], filename: str) -> None:
    """
    Write CSV with columns:
      SeasonEpisode, Date, AbsEpisode, Title, TargetFilename
    """
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SeasonEpisode", "Date", "AbsEpisode", "Title", "TargetFilename"])

        for ep in episodes:
            w.writerow(
                [
                    ep.season_episode_code,
                    ep.air_date_iso,
                    ep.abs_episode if ep.abs_episode is not None else "",
                    ep.title,
                    ep.target_filename,
                ]
            )


def write_json(episodes: List[Episode], filename: str) -> None:
    """
    Write JSON list of episodes.
    Each episode includes:
      season_episode_code, season_raw, ep_in_season, title,
      air_date_iso, abs_episode, target_filename
    """
    data = [asdict(ep) for ep in episodes]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    episodes = fetch_all_episodes_from_allseasons()
    assign_absolute_numbers_and_filenames(episodes)

    csv_file = "eisenbahn_romantik_tvdb_episodes.csv"
    json_file = "eisenbahn_romantik_tvdb_episodes.json"

    write_csv(episodes, csv_file)
    print(f"CSV written to: {csv_file}")

    write_json(episodes, json_file)
    print(f"JSON written to: {json_file}")


if __name__ == "__main__":
    main()
