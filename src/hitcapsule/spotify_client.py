from __future__ import annotations
from typing import Iterable, Optional, List, Tuple
import logging
import os
import time
import re
import difflib
import base64

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ------------------------ Benzerlik / Temizleme ------------------------

def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

_APOSTROPHE_FIX = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
def _unify_quotes(text: str) -> str: return text.translate(_APOSTROPHE_FIX)

_PAREN_RE = re.compile(r"\([^)]*\)")
_BRACK_RE = re.compile(r"\[[^]]*\]")
def _strip_brackets(text: str) -> str:
    text = _PAREN_RE.sub("", text)
    text = _BRACK_RE.sub("", text)
    return text

def _collapse_spaces(text: str) -> str: return " ".join(text.split()).strip()

def _sanitize_title(title: str) -> str:
    title = _unify_quotes(title)
    title = _strip_brackets(title)
    return _collapse_spaces(title)

_SPLIT_RE = re.compile(r"\s*(?:,|&| x |×| with | and | feat\.| featuring | ft\.|\+)\s*", flags=re.IGNORECASE)
def _primary_artist(artist: str) -> str:
    artist = _collapse_spaces(_unify_quotes(artist or ""))
    parts = _SPLIT_RE.split(artist) if artist else []
    return parts[0] if parts else artist

def _title_candidates(want_title: str) -> List[str]:
    base = _sanitize_title(want_title or "")
    cands = [base]
    if "/" in base or " | " in base:
        import re as _re
        parts = _re.split(r"/|\s\|\s", base)
        parts = [p.strip() for p in parts if p and len(p.strip()) > 1]
        for p in parts:
            if p not in cands: cands.append(p)
    return cands

# ----------------------------------------------------------------------

class SpotifyClient:
    def __init__(self, market: Optional[str] = None, enable_cover_upload: bool = False) -> None:
        load_dotenv()
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
        if not all([client_id, client_secret, redirect_uri]):
            raise RuntimeError("Missing Spotify credentials in environment (.env).")

        # Scopes: public+private; kapak için opsiyonel ugc-image-upload
        scopes = ["playlist-modify-private", "playlist-modify-public"]
        if enable_cover_upload:
            scopes.append("ugc-image-upload")
        scope = ",".join(scopes)

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

        # Market: parametre > ENV > "US"
        self.market = (market or os.getenv("SPOTIFY_MARKET") or "US").upper()

        me = self.sp.current_user()
        self.user_id = me["id"]
        logger.info("Authenticated as %s", me.get("display_name", self.user_id))

    # ------------------------------- Playlist helpers -------------------------------

    def create_playlist(self, name: str, public: bool = False, description: str = "") -> str:
        playlist = self.sp.user_playlist_create(user=self.user_id, name=name, public=public, description=description)
        logger.info("Created playlist: %s (%s)", name, playlist["id"])
        return playlist["id"]

    def get_playlist_url(self, playlist_id: str) -> str:
        pl = self.sp.playlist(playlist_id, fields="external_urls")
        return pl["external_urls"]["spotify"]

    def add_items_chunked(self, playlist_id: str, uris: Iterable[str], chunk: int = 100) -> None:
        batch: List[str] = []
        for uri in uris:
            batch.append(uri)
            if len(batch) == chunk:
                self.sp.playlist_add_items(playlist_id=playlist_id, items=batch)
                batch = []
        if batch:
            self.sp.playlist_add_items(playlist_id=playlist_id, items=batch)

    def replace_items(self, playlist_id: str, uris: List[str]) -> None:
        """Tüm içeriği uris ile değiştir (ilk 100 replace, kalanı append)."""
        first = uris[:100]
        rest  = uris[100:]
        self.sp.playlist_replace_items(playlist_id, first)
        if rest:
            self.add_items_chunked(playlist_id, rest, chunk=100)

    def upload_cover_image(self, playlist_id: str, image_path: str) -> bool:
        """JPEG'yi base64 string olarak yükler. Scope yoksa False döner."""
        try:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            self.sp.playlist_upload_cover_image(playlist_id, b64)
            return True
        except spotipy.SpotifyException as e:
            logger.warning("Cover upload failed: %s", e)
            return False

    def _iter_my_playlists(self, limit: int = 50):
        """Kullanıcının tüm playlist’lerini sayfalar halinde getir."""
        offset = 0
        while True:
            page = self.sp.current_user_playlists(limit=limit, offset=offset)
            items = page.get("items", [])
            if not items:
                break
            for it in items:
                yield it
            offset += len(items)
            if offset >= page.get("total", 0):
                break

    def find_playlist_by_name(self, name: str) -> Optional[Tuple[str, dict]]:
        """İsme birebir (case-insensitive) eşleşen ilk playlist'i getir."""
        target = (name or "").strip().lower()
        for it in self._iter_my_playlists():
            if (it.get("name") or "").strip().lower() == target:
                return it["id"], it
        return None

    def upsert_playlist_with_items(self, name: str, public: bool, description: str, uris: List[str], replace: bool = True) -> Tuple[str, bool]:
        """
        Aynı isimde playlist varsa:
          - replace=True -> içeriği tamamen bu uris ile değiştir (güncelle)
          - replace=False -> var olana ekle
        Yoksa yeni oluştur.
        Dönüş: (playlist_id, created_new: bool)
        """
        found = self.find_playlist_by_name(name)
        if found:
            pid, meta = found
            # Detayları senkronla (public/description değişmiş olabilir)
            try:
                self.sp.playlist_change_details(pid, name=name, public=public, description=description)
            except Exception as e:
                logger.warning("playlist_change_details failed: %s", e)
            if replace:
                self.replace_items(pid, uris)
            else:
                self.add_items_chunked(pid, uris, chunk=100)
            logger.info("Updated existing playlist: %s (%s)", name, pid)
            return pid, False
        else:
            pid = self.create_playlist(name=name, public=public, description=description)
            if uris:
                self.add_items_chunked(pid, uris, chunk=100)
            return pid, True

    # -------------------------------- Search --------------------------------

    def _score_candidate(self, cand_title: str, cand_artists: str, want_title: str, want_artist: str, popularity: int) -> float:
        s_title = _similar(want_title, cand_title)
        s_artist = _similar(want_artist, cand_artists) if want_artist else 0.5
        pop_norm = (popularity or 0) / 100.0
        return (0.6 * s_title) + (0.25 * s_artist) + (0.15 * pop_norm)

    def _run_query(self, q: str, limit: int = 10):
        try:
            logger.debug("Spotipy search q=%s market=%s", q, self.market)
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
        primary = _primary_artist(artist)
        title_opts = _title_candidates(title)

        def _queries(t: str) -> List[str]:
            qs: List[str] = []
            if primary:
                if year:
                    qs.append(f'track:"{t}" artist:"{primary}" year:{year}')
                qs.append(f'track:"{t}" artist:"{primary}"')
            if year:
                qs.append(f'track:"{t}" year:{year}')
            qs.append(f'track:"{t}"')
            return qs

        for t in title_opts:
            norm_t = _sanitize_title(t)
            for q in _queries(norm_t):
                res = self._run_query(q, limit=10)
                items = (res or {}).get("tracks", {}).get("items", [])
                if not items:
                    continue

                best_uri = None
                best_score = -1.0
                for it in items:
                    cand_title = _sanitize_title(it["name"])
                    cand_artists = ", ".join(a["name"] for a in it["artists"])
                    score = self._score_candidate(cand_title, cand_artists, norm_t, primary, it.get("popularity", 0))
                    if score > best_score:
                        best_score = score
                        best_uri = it["uri"]
                if best_uri:
                    return best_uri
        return None
