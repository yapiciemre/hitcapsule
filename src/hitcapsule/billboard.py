from __future__ import annotations
from dataclasses import dataclass
from typing import List
import logging
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) "
    "Gecko/20100101 Firefox/131.0"
)
BASE_URL = "https://www.billboard.com/charts/hot-100/"

@dataclass
class ChartEntry:
    rank: int
    title: str
    artist: str

def _clean(text: str) -> str:
    return " ".join(text.split()).strip()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6))
def _fetch_html(url: str) -> str:
    logger.info("Fetching Billboard page: %s", url)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text

def fetch_hot100(date_yyyy_mm_dd: str) -> List[ChartEntry]:
    """
    Fetches Billboard Hot 100 for a given date.
    Returns list of ChartEntry(rank, title, artist).
    Uses multiple selector fallbacks to be resilient to minor HTML changes.
    """
    html = _fetch_html(BASE_URL + date_yyyy_mm_dd)
    soup = BeautifulSoup(html, "html.parser")

    entries: List[ChartEntry] = []

    # Primary strategy: iterate chart items when present
    items = soup.select("li.o-chart-results-list__item")
    if items:
        rank = 0
        for li in items:
            # Title fallbacks
            title_el = (
                li.select_one("h3#title-of-a-story") or
                li.select_one("h3.c-title") or
                li.select_one("h3")
            )
            # Artist fallbacks
            artist_el = (
                li.select_one("span.c-label.a-no-truncate") or
                li.select_one("span.a-no-truncate") or
                li.select_one("span.c-label") or
                li.select_one("span")
            )
            if title_el:
                rank += 1
                title = _clean(title_el.get_text())
                artist = _clean(artist_el.get_text()) if artist_el else ""
                entries.append(ChartEntry(rank=rank, title=title, artist=artist))

    # Fallback strategy: older/simple structure (common tutorial selector)
    if not entries:
        titles = [t.get_text().strip() for t in soup.select("li ul li h3")]
        # artists may be next siblings or nearby spans; best-effort
        artist_candidates = [a.get_text().strip() for a in soup.select("li ul li span")]
        for i, title in enumerate(titles, start=1):
            artist = artist_candidates[i - 1] if i - 1 < len(artist_candidates) else ""
            entries.append(ChartEntry(rank=i, title=_clean(title), artist=_clean(artist)))

    # Normalize length to at most 100 and filter empty titles
    entries = [e for e in entries if e.title]
    # Deduplicate while preserving order (some pages render extras)
    seen = set()
    deduped: List[ChartEntry] = []
    for e in entries:
        key = (e.title.lower(), e.artist.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    # Keep top 100
    deduped = deduped[:100]
    # Fix ranks
    for idx, e in enumerate(deduped, start=1):
        e.rank = idx

    logger.info("Fetched %d chart entries", len(deduped))
    return deduped
