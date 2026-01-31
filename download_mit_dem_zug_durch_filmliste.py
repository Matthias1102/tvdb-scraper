#!/usr/bin/env python3
"""
Scrape all episode titles + air dates from TVDB "All seasons / Official" page
and write an Excel table with the requested columns.

Output columns:
- EasonEpisode: SxxEyy where xx is the "year index" (season number starting at 01),
               and yy is the episode number within that season.
- Broadcast Date: yyyy-mm-dd
- absolute episode number
- Title as mentioned in TVDB
- Title in the form: "SxxEyy - Mit dem Zug durch ... .mp4" ( ... = Title )

Requires:
  pip install requests beautifulsoup4 openpyxl
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.table import Table, TableStyleInfo


URL = "https://www.thetvdb.com/series/280509-show/allseasons/official"
OUT_XLSX = "tvdb_episodes.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

SXXEYY_RE = re.compile(r"\bS(\d{1,3})E(\d{1,4})\b", re.IGNORECASE)

# Windows-forbidden filename chars: \ / : * ? " < > |
BAD_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


@dataclass
class Episode:
    season: int
    episode: int
    airdate_iso: Optional[str]  # yyyy-mm-dd or None
    title: str


def clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def sanitize_filename_component(s: str) -> str:
    s = clean_spaces(s)
    s = BAD_FILENAME_CHARS_RE.sub(" ", s)
    s = clean_spaces(s)
    return s


def parse_airdate_to_iso(date_text: str) -> Optional[str]:
    """
    TVDB page typically shows dates like: 'July 10, 2006'
    Convert to '2006-07-10'. If parsing fails, return None.
    """
    date_text = clean_spaces(date_text)
    try:
        dt = datetime.strptime(date_text, "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def extract_episodes(html: str) -> List[Episode]:
    soup = BeautifulSoup(html, "html.parser")

    episodes: List[Episode] = []

    # On this TVDB page, each episode appears as an <h4> with text like "S01E01" and an <a> containing the title.
    # The air date is usually in the same parent <li> under a nested <ul> with an <li> containing the date.
    for h4 in soup.find_all("h4"):
        h4_text = clean_spaces(h4.get_text(" ", strip=True))
        m = SXXEYY_RE.search(h4_text)
        if not m:
            continue

        season = int(m.group(1))
        epnum = int(m.group(2))

        # Title: prefer the <a> inside the h4
        a = h4.find("a")
        title = clean_spaces(a.get_text(" ", strip=True)) if a else None
        if not title:
            # Fallback: remove SxxEyy from the header text
            title = clean_spaces(SXXEYY_RE.sub("", h4_text)).strip("-–—|• ").strip()

        # Find air date in the closest containing <li>
        airdate_iso: Optional[str] = None
        container_li = h4.find_parent("li")
        if container_li:
            # Look for list items within the container that resemble "Month dd, yyyy"
            # (We only need the first one that parses.)
            for li in container_li.find_all("li"):
                candidate = clean_spaces(li.get_text(" ", strip=True))
                iso = parse_airdate_to_iso(candidate)
                if iso:
                    airdate_iso = iso
                    break

        episodes.append(Episode(season=season, episode=epnum, airdate_iso=airdate_iso, title=title))

    # Sort by season then episode
    episodes.sort(key=lambda e: (e.season, e.episode))
    return episodes


def write_excel(episodes: List[Episode], out_path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Episodes"

    headers = [
        "EasonEpisode",
        "Broadcast Date",
        "absolute episode number",
        "Title (TVDB)",
        'Title as "SxxEyy - Mit dem Zug durch ... .mp4"',
    ]
    ws.append(headers)

    for idx, e in enumerate(episodes, start=1):
        eason_episode = f"S{e.season:02d}E{e.episode:02d}"
        safe_title = sanitize_filename_component(e.title)
        filename_title = f"{eason_episode} - Mit dem Zug durch {safe_title}.mp4"

        ws.append([
            eason_episode,
            e.airdate_iso or "",
            idx,
            e.title,
            filename_title,
        ])

    # Style header
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Column widths (reasonable defaults)
    col_widths = [14, 14, 22, 45, 60]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    ws.freeze_panes = "A2"

    # Add an Excel "Table" (filterable)
    last_row = ws.max_row
    last_col = ws.max_column
    table_ref = f"A1:{chr(64 + last_col)}{last_row}"
    table = Table(displayName="EpisodesTable", ref=table_ref)
    style = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    table.tableStyleInfo = style
    ws.add_table(table)

    wb.save(out_path)


def main() -> None:
    html = fetch_html(URL)
    episodes = extract_episodes(html)

    if not episodes:
        raise SystemExit(
            "No episodes parsed. TVDB may have changed markup or blocked the request.\n"
            "Tip: try running again, or fetch with a logged-in session/cookies if needed."
        )

    write_excel(episodes, OUT_XLSX)
    print(f"Wrote {len(episodes)} rows to {OUT_XLSX}")


if __name__ == "__main__":
    main()
