from __future__ import annotations
from typing import Iterable, Optional, List
import logging
import os
import time
import re
import difflib

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# ------------------------ Benzerlik / Temizleme Yardımcıları ------------------------

def _similar(a: str, b: str) -> float:
    """Case-insensitive benzerlik skoru (0..1)."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


_APOSTROPHE_FIX = str.maketrans({
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-",
})

def _unify_quotes(text: str) -> str:
    return text.translate(_APOSTROPHE_FIX)

_PAREN_RE = re.compile(r"\([^)]*\)")
_BRACK_RE = re.compile(r"\[[^]]*\]")

def _strip_brackets(text: str) -> str:
    """(Radio Edit), [Live] gibi parantez içlerini kaldır."""
    text = _PAREN_RE.sub("", text)
    text = _BRACK_RE.sub("", text)
    return text

def _collapse_spaces(text: str) -> str:
    return " ".join(text.split()).strip()

def _sanitize_title(title: str) -> str:
    """Başlığı normalize et: tırnak/parantez/boşluk düzeltmeleri."""
    title = _unify_quotes(title)
    title = _strip_brackets(title)
    title = _collapse_spaces(title)
    return title

# Çoklu sanatçı dizelerini ayır (virgül, &, feat., with, x, +, vs.)
_SPLIT_RE = re.compile(
    r"\s*(?:,|&| x |×| with | and | feat\.| featuring | ft\.|\+)\s*",
    flags=re.IGNORECASE,
)

def _primary_artist(artist: str) -> str:
    """Karma sanatçı dizelerinden birincil sanatçıyı çıkar."""
    artist = _unify_quotes(artist or "")
    artist = _collapse_spaces(artist)
    if not artist:
        return artist
    parts = _SPLIT_RE.split(artist)
    return parts[0] if parts else artist

def _title_candidates(want_title: str) -> List[str]:
    """
    A/B single veya çift başlık durumlarında (örn. 'Song A / Song B')
    önce tam başlığı, sonra parçalanmış alt başlıkları dener.
    """
    base = _sanitize_title(want_title or "")
    cands = [base]
    if "/" in base or " | " in base:
        parts = re.split(r"/|\s\|\s", base)
        parts = [p.strip() for p in parts if p and len(p.strip()) > 1]
        for p in parts:
            if p not in cands:
                cands.append(p)
    return cands

# ------------------------------------------------------------------------------------


class SpotifyClient:
    def __init__(self) -> None:
        load_dotenv()  # .env dosyasını yükle

        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
        if not all([client_id, client_secret, redirect_uri]):
            raise RuntimeError("Missing Spotify credentials in environment (.env).")

        scope = "playlist-modify-private"
        cache_dir = os.path.join(os.getcwd(), ".cache")
        os.makedirs(cache_dir, exist_ok=True)

        self.sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=scope,
                open_browser=True,
                cache_path=os.path.join(cache_dir, "spotipy_cache"),
                show_dialog=True,
            ),
            requests_timeout=20,
        )

        # .env ile pazarı seçebilirsin (US/TR/…)
        self.market = os.getenv("SPOTIFY_MARKET", "US") or None

        me = self.sp.current_user()
        self.user_id = me["id"]
        logger.info("Authenticated as %s", me.get("display_name", self.user_id))

    # ------------------------------- Playlist Helpers -------------------------------

    def create_playlist(self, name: str, public: bool = False, description: str = "") -> str:
        playlist = self.sp.user_playlist_create(
            user=self.user_id,
            name=name,
            public=public,
            description=description,
        )
        logger.info("Created playlist: %s (%s)", name, playlist["id"])
        return playlist["id"]

    def add_items_chunked(self, playlist_id: str, uris: Iterable[str], chunk: int = 100) -> None:
        batch: List[str] = []
        for uri in uris:
            batch.append(uri)
            if len(batch) == chunk:
                self.sp.playlist_add_items(playlist_id=playlist_id, items=batch)
                batch = []
        if batch:
            self.sp.playlist_add_items(playlist_id=playlist_id, items=batch)

    # --------------------------------- Search Core ----------------------------------

    def _score_candidate(
        self,
        cand_title: str,
        cand_artists: str,
        want_title: str,
        want_artist: str,
        popularity: int,
    ) -> float:
        """Aday şarkıyı başlık/sanatçı benzerliği ve popülerliğe göre puanla."""
        s_title = _similar(want_title, cand_title)
        s_artist = _similar(want_artist, cand_artists) if want_artist else 0.5
        pop_norm = (popularity or 0) / 100.0
        # Başlık ağırlıklı, ardından sanatçı ve biraz da popülerlik
        return (0.6 * s_title) + (0.25 * s_artist) + (0.15 * pop_norm)

    def _run_query(self, q: str, limit: int = 10):
        """Spotipy aramasını çalıştır; 429 durumunda bekleyip tekrar dene."""
        try:
            logger.debug("Spotipy search q=%s", q)
            return self.sp.search(q=q, type="track", limit=limit, market=self.market)
        except spotipy.exceptions.SpotifyException as e:
            if getattr(e, "http_status", None) == 429:
                retry_after = int(getattr(e, "headers", {}).get("Retry-After", 2))
                logger.warning("Rate-limited by Spotify. Sleeping %s sec…", retry_after)
                time.sleep(retry_after)
                return self._run_query(q, limit)
            logger.error("Spotify error: %s", e)
            return None
        except Exception as e:
            logger.warning("Search failed: %s", e)
            return None

    def search_best_track(self, title: str, artist: str, year: str) -> Optional[str]:
        """
        Yüksek erişim için kademeli sorgu stratejisi:
          1) track + primary artist + year
          2) track + primary artist
          3) track + year
          4) track (sadece)
        Başlık adayları: [tam başlık, split parçalar]
        """
        primary = _primary_artist(artist)
        title_opts = _title_candidates(title)

        def _queries(t: str) -> List[str]:
            qs: List[str] = []
            if primary:
                qs.append(f'track:"{t}" artist:"{primary}" year:{year}')
                qs.append(f'track:"{t}" artist:"{primary}"')
            qs.append(f'track:"{t}" year:{year}')
            qs.append(f'track:"{t}"')
            return qs

        for t in title_opts:                 # önce tam başlık, sonra A/B split parçalar
            norm_t = _sanitize_title(t)
            for q in _queries(norm_t):       # her başlık için kademeli sorgular
                res = self._run_query(q, limit=10)
                items = (res or {}).get("tracks", {}).get("items", [])
                if not items:
                    continue

                best_uri = None
                best_score = -1.0
                for it in items:
                    cand_title = _sanitize_title(it["name"])
                    cand_artists = ", ".join(a["name"] for a in it["artists"])
                    score = self._score_candidate(
                        cand_title, cand_artists, norm_t, primary, it.get("popularity", 0)
                    )
                    if score > best_score:
                        best_score = score
                        best_uri = it["uri"]

                if best_uri:
                    return best_uri

        # Hiç bulunamadı
        return None
