#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import lzma
import re
from pathlib import Path
from typing import Iterable, List, Optional

import requests


FILMLISTE_URL = "https://liste.mediathekview.de/Filmliste-akt.xz"


def _norm(s: str) -> str:
    s = s.lower()
    s = s.replace("–", "-").replace("—", "-")
    return s


def _is_er_record(record: list) -> bool:
    """
    Heuristic filter: match if any string field contains both
    'eisenbahn' and 'romantik' (covers Eisenbahn-Romantik and Eisenbahn Romantik).
    """
    for v in record:
        if isinstance(v, str):
            t = _norm(v)
            if "eisenbahn" in t and "romantik" in t:
                return True
    return False


def download_filmliste_extract_er(
    url: str = FILMLISTE_URL,
    *,
    out_json: Optional[str | Path] = None,
    timeout: int = 120,
    chunk_size: int = 1024 * 1024,
    max_matches: Optional[int] = None,
) -> List[list]:
    """
    Download MediathekView Filmliste-akt.xz and extract only Eisenbahn-Romantik records.

    Important: Filmliste is not strict JSON (duplicate keys like "X" repeat). :contentReference[oaicite:1]{index=1}
    Therefore we do NOT json.load() the full document. We scan for each '"X": <array>' occurrence.

    Args:
        url: Filmliste XZ URL.
        out_json: If provided, write the filtered records as a JSON array to this file.
        timeout: HTTP timeout seconds.
        chunk_size: Download chunk size.
        max_matches: Optional cap for debugging.

    Returns:
        List of film records (each record is a list).
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ER-Filmliste-Extractor/1.0)"}
    r = requests.get(url, headers=headers, stream=True, timeout=timeout)
    r.raise_for_status()

    # Stream-decompress XZ
    lz = lzma.LZMADecompressor()

    # We'll scan decompressed TEXT for repeated '"X":' entries.
    # Keep a rolling buffer because a record can span chunks.
    text_buf = ""

    # Find '"X"' token and then parse the following JSON array.
    token = '"X"'
    dec = json.JSONDecoder()

    matches: List[list] = []

    for chunk in r.iter_content(chunk_size=chunk_size):
        if not chunk:
            continue

        decompressed = lz.decompress(chunk)
        if not decompressed:
            continue

        text_buf += decompressed.decode("utf-8", errors="ignore")

        # Scan buffer for '"X"' occurrences; parse arrays after the colon.
        i = 0
        while True:
            j = text_buf.find(token, i)
            if j < 0:
                # Keep tail to handle token split across chunks
                text_buf = text_buf[max(0, len(text_buf) - 200_000) :]
                break

            # Expect pattern: "X":<whitespace><array>
            k = j + len(token)
            # Find the ':' after "X"
            colon = text_buf.find(":", k)
            if colon < 0:
                # Need more data
                break

            # Skip whitespace to the start of the JSON value
            pos = colon + 1
            while pos < len(text_buf) and text_buf[pos].isspace():
                pos += 1

            # We only care about arrays after "X":
            if pos >= len(text_buf) or text_buf[pos] != "[":
                i = pos
                continue

            try:
                record, end = dec.raw_decode(text_buf, pos)
            except json.JSONDecodeError:
                # Incomplete array: wait for more decompressed data
                break

            if isinstance(record, list) and _is_er_record(record):
                matches.append(record)
                if max_matches is not None and len(matches) >= max_matches:
                    if out_json:
                        Path(out_json).write_text(
                            json.dumps(matches, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    return matches

            # Continue scanning after this parsed array
            i = end

        # continue downloading/decompressing

    if out_json:
        out_path = Path(out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")

    return matches


if __name__ == "__main__":
    er = download_filmliste_extract_er(out_json="MediathekView-Eisenbahn-Romantik.json")
    print(f"Extracted {len(er)} Eisenbahn-Romantik records")
