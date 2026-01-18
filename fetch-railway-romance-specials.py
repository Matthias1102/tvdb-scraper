#! /usr/bin/env python3
"""
fetch-railway-romance-specials.py
---------------------------------

This script downloads the episode list for the *specials* (Season 0) of the TV
series "Eisenbahn-Romantik" from TheTVDB's public Season 0 page:

    https://thetvdb.com/series/railway-romance/seasons/official/0

It extracts:
  • season/episode codes (specials are forced to S0000Enn)
  • air dates (converted to YYYY-MM-DD when possible)
  • absolute episode numbers (sequential 1..N within specials list)
  • titles (as provided by TheTVDB)
  • a suggested target filename for each episode

Two output files are generated in the script directory:
    eisenbahn_romantik_tvdb_specials.csv
    eisenbahn_romantik_tvdb_specials.json

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
    python fetch-railway-romance-specials.py

Notes:
  • This script does *not* rely on TheTVDB’s API, only on the public HTML pages.
  • Specials (Season 0) are given a year code of "0000" → e.g. S0000E01.
  • Absolute episode numbers are assigned in the order after sorting by ep_in_season.
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

SPECIALS_URL = "https://thetvdb.com/series/railway-romance/seasons/official/0"
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
    season_episode_code: str  # S00Enn for specials (we'll store as S0000Enn)
    season_raw: int           # 0 for specials
    ep_in_season: int         # Episode number within season 0
    title: str
    air_date_iso: str         # yyyy-mm-dd or "" (if missing/unparseable)
    abs_episode: Optional[int] = None  # 1..N (within specials list)
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


def fetch_specials() -> List[Episode]:
    """
    Fetch specials from TheTVDB Season 0 page and return a list of Episode objects.
    Tries to be resilient to minor HTML variations by:
      - finding all episode links
      - reading surrounding text for S0E.. patterns and dates
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ER-TVDB-Scraper/2.0; +https://example.com/)"
        )
    }

    print(f"Loading Specials (Season 0) page: {SPECIALS_URL}")
    resp = requests.get(SPECIALS_URL, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Episodes on season pages are typically linked like:
    # /series/railway-romance/episodes/<id>
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

        # Use parent <tr> or <li> as context (TVDB sometimes uses tables on season pages)
        container = a.find_parent(["tr", "li", "div"])
        text_block = (
            container.get_text(" ", strip=True)
            if container is not None
            else a.get_text(" ", strip=True)
        )

        # We only want specials (season 0). Match patterns like:
        #   S0E1, S00E01, S0 E1 (rare), etc.
        m = re.search(r"S\s*0+\s*E\s*(\d{1,3})", text_block, flags=re.IGNORECASE)
        if not m:
            # Sometimes TVDB may omit the 'S0E..' prefix in the visible text.
            # As a fallback, try to find an explicit episode number label like "Episode 12".
            m2 = re.search(r"\bEpisode\s+(\d{1,3})\b", text_block, flags=re.IGNORECASE)
            if not m2:
                continue
            ep_in_season = int(m2.group(1))
        else:
            ep_in_season = int(m.group(1))

        season_raw = 0
        # Specials are forced to S0000Enn (year code "0000")
        season_episode_code = f"S{0:04d}E{ep_in_season:02d}"  # S0000E01 ...

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

    # Deduplicate by (season_raw, ep_in_season, title) just in case multiple links exist per row.
    uniq = {}
    for ep in episodes:
        key = (ep.season_raw, ep.ep_in_season, ep.title)
        uniq[key] = ep
    episodes = list(uniq.values())

    # Order by episode number within specials
    episodes.sort(key=lambda e: e.ep_in_season)

    print(f"Found {len(episodes)} specials.")
    return episodes


def assign_absolute_numbers_and_filenames(episodes: List[Episode]) -> None:
    """
    Assign absolute episode numbers 1..N within the specials list, and build target filenames.
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
    Write JSON list of specials.
    """
    data = [asdict(ep) for ep in episodes]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    episodes = fetch_specials()
    assign_absolute_numbers_and_filenames(episodes)

    csv_file = "eisenbahn_romantik_tvdb_specials.csv"
    json_file = "eisenbahn_romantik_tvdb_specials.json"

    write_csv(episodes, csv_file)
    print(f"CSV written to: {csv_file}")

    write_json(episodes, json_file)
    print(f"JSON written to: {json_file}")


if __name__ == "__main__":
    main()
