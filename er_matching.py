"""
er_matching.py
--------------

Helpers for Eisenbahn-Romantik video filename handling and episode matching:

- normalize(text)
- strip_series_prefix(text)
- extract_raw_title_from_filename(path)
- load_episodes(json_path)
- find_best_match(title, episodes)   # includes exact containment rule
- build_new_filename(ep)
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------------------------------------------------
# Normalization helpers
# ----------------------------------------------------------------------

def normalize(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u00df", "ss")
    s = s.replace("_", " ")
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if c.isalnum() or c.isspace())
    s = re.sub(r"\s+", " ", s).strip()
    return s


SERIES_PREFIX_RE = re.compile(
    r"""^\s*
        eisenbahn\s*[-–—]?\s*romantik
        \s*(?:[:\-–—]\s*)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_series_prefix(s: str) -> str:
    if not s:
        return ""
    return SERIES_PREFIX_RE.sub("", s).strip()


# ----------------------------------------------------------------------
# Episode loading
# ----------------------------------------------------------------------

def load_episodes(json_path: str) -> List[Dict[str, Any]]:
    """
    Load episodes from TVDB-export JSON and enrich each entry with normalized titles:
      - norm_title
      - norm_title_noprefix
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    episodes: List[Dict[str, Any]] = []
    for ep in data:
        title = ep.get("title", "") or ""
        episodes.append(
            {
                "season_episode_code": ep.get("season_episode_code", "") or "",
                "air_date_iso": ep.get("air_date_iso", "") or "",
                "abs_episode": ep.get("abs_episode"),
                "title": title,
                "norm_title": normalize(title),
                "norm_title_noprefix": normalize(strip_series_prefix(title)),
            }
        )

    return episodes


# ----------------------------------------------------------------------
# Filename parsing
# ----------------------------------------------------------------------

def extract_raw_title_from_filename(filename: str) -> str:
    """
    Extract a human-readable title from a downloaded MP4 filename.

    Current rules (kept from your script):
      - drop leading "Eisenbahn Romantik" variants
      - drop trailing numeric IDs like " - 12345"
      - "_" -> " "
    """
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r"^Eisenbahn[- ]?Romantik[- ]*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[- ]\d{5,}$", "", name).strip()
    name = name.replace("_", " ")
    return name.strip()


# ----------------------------------------------------------------------
# Matching logic
# ----------------------------------------------------------------------

def contains_whole_query(query: str, candidate: str) -> bool:
    """
    Word-ish containment check (simple, but effective with normalized strings).
    Ensures 'nonstalbahn' matches inside longer titles, but not as a substring
    of something else without boundaries.
    """
    if not query or not candidate:
        return False
    return f" {query} " in f" {candidate} "


def find_best_match(title: str, episodes: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    Find the best matching episode for a given raw title.

    Strategy:
      1) normalize + strip series prefix from query
      2) HARD RULE: if query is contained as a whole token sequence in candidate,
         return immediately (score=1.0)
      3) otherwise fall back to SequenceMatcher ratio on normalized strings
    """
    norm_title = normalize(strip_series_prefix(title))
    if not norm_title:
        return None, 0.0

    best_ep: Optional[Dict[str, Any]] = None
    best_score = 0.0

    for ep in episodes:
        cand = ep.get("norm_title_noprefix", "")
        if not cand:
            continue

        # Hard rule: exact containment wins
        if contains_whole_query(norm_title, cand):
            return ep, 1.0

        score = SequenceMatcher(None, norm_title, cand).ratio()
        if score > best_score:
            best_score = score
            best_ep = ep

    return best_ep, best_score


# ----------------------------------------------------------------------
# Filename construction
# ----------------------------------------------------------------------

def sanitize_for_filename(s: str) -> str:
    if not s:
        return ""
    s = s.replace("/", "-").replace("\\", "-")
    s = re.sub(r'[:*?"<>|]', "", s)
    return s.strip()


def build_new_filename(ep: Dict[str, Any]) -> str:
    season_code = ep.get("season_episode_code") or "S00E00"
    air_date = ep.get("air_date_iso") or "0000-00-00"
    abs_ep = ep.get("abs_episode")
    abs_ep_str = str(abs_ep) if abs_ep is not None else "0"
    title = sanitize_for_filename(ep.get("title") or "Unknown Title")
    return f"Eisenbahn-Romantik {season_code} - {air_date} - {abs_ep_str} - {title}.mp4"
