import os, sys, time
from datetime import date as _date

# src yolunu ekle ki import çalışsın
BASE = os.path.dirname(__file__)
SRC = os.path.join(BASE, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import streamlit as st
from itertools import zip_longest
from hitcapsule.billboard import fetch_hot100
from hitcapsule.spotify_client import SpotifyClient
from hitcapsule.artwork import make_cover, make_story_poster

# ---- Sayfa ayarları ----
st.set_page_config(page_title="HitCapsule", page_icon="🎵", layout="wide")

# ---- Global stiller (tabs + kart + badge + callout + buton + toolbar/separator) ----
st.markdown("""
<style>
/* Tabs: üstteki barı kaldır, sadece underline kalsın */
.stTabs [data-baseweb="tab-list"]{
  background: transparent !important; border:0 !important; box-shadow:none !important; padding:0 !important; gap:0 !important;
}
.stTabs [data-baseweb="tab"]{
  background: transparent !important; border:0 !important; margin:0 24px 0 0 !important; padding:0 0 10px 0 !important;
}
.stTabs [data-baseweb="tab"] p{ font-weight:600 !important; color:rgba(255,255,255,.65) !important; margin:0 !important; }
.stTabs [aria-selected="true"] p{ color:#fff !important; }
.stTabs [data-baseweb="tab-highlight"]{ background-color:#22c55e !important; height:2px !important; border-radius:0 !important; }

/* Basit kart / rozet / callout */
.hc-card{ background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.08); border-radius:12px; padding:16px; }
.hc-badge{ display:inline-block; background:rgba(34,197,94,.12); color:#d1fae5; border:1px solid rgba(34,197,94,.35);
  padding:6px 10px; border-radius:999px; font-size:0.9rem; }
.hc-muted{ color:rgba(255,255,255,.65) }
.hc-callout{ margin-top:8px; padding:12px 14px; border-radius:12px; background:rgba(255,255,255,.03); border:1px dashed rgba(255,255,255,.1); }

/* Submit butonu: Spotify yeşili */
form [data-testid="stFormSubmitButton"] button{
  background:#1DB954 !important; color:#0b0f14 !important; border:0 !important; border-radius:10px !important;
  font-weight:700 !important; padding:.6rem 1rem !important;
}
form [data-testid="stFormSubmitButton"] button:hover{ filter:brightness(1.05); }

/* Toolbar + separator */
.hc-toolbar{ background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.08); border-radius:12px;
  padding:10px 14px; margin: 6px 0 6px; }
.hc-sep{ border:none; height:1px; background:rgba(255,255,255,.08); margin:8px 0 16px; }
</style>
""", unsafe_allow_html=True)

st.title("HitCapsule — Pick a date. Press play.")
st.caption("Create a Spotify playlist from the Billboard Hot 100 of any date.")

# Billboard Hot 100 ilk yayın: 1958-08-04
BILLBOARD_START = _date(1958, 8, 4)
TODAY = _date.today()

# 🔹 FULL-WIDTH TOOLBAR: Toggle burada (iki kolonun üstünde, hizayı eşitler)
tb_l, tb_r = st.columns([1, 1])
with tb_l:
    blend_mode = st.toggle(
        "Bestie Blend (two dates)",
        value=st.session_state.get("blend_mode", False),
        key="blend_mode",
        help="Two dates are interleaved (A,B,A,B…) with dedupe."
    )
with tb_r:
    # burayı ileride kısa açıklama / badge için kullanabilirsin
    st.write("")

# ---- İki kolon düzeni ----
left, right = st.columns([1, 1])

with left:
    with st.form("controls"):
        # --- Tarih(ler) ---
        d1 = st.date_input(
            "Pick a date" if not blend_mode else "Pick first date",
            value=_date(1997, 3, 6),
            min_value=BILLBOARD_START,
            max_value=TODAY,
            format="YYYY/MM/DD",
            help="Billboard Hot 100 started in 1958. You can pick any date up to today."
        )
        d2 = None
        if blend_mode:
            d2 = st.date_input(
                "Pick second date",
                value=_date(1998, 4, 20),
                min_value=BILLBOARD_START,
                max_value=TODAY,
                format="YYYY/MM/DD",
                help="Billboard Hot 100 started in 1958. You can pick any date up to today."
            )

        custom_name = st.text_input("Playlist name (optional)", "")
        make_public = st.checkbox("Create as public", value=False)
        upload_cover = st.checkbox("Upload custom cover (requires extra Spotify scope)", value=False)
        submitted = st.form_submit_button("Create My Playlist")

    # Tips
    st.markdown(
        """
        <div class="hc-callout">
            <b>💡 Tip:</b> <span class="hc-muted">
            If you choose public, your playlist can be seen by everyone.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="hc-callout">
            <b>💡 Tip:</b> <span class="hc-muted">
            In <b>Bestie Blend</b> mode, the lists of two dates are mixed in order (A,B,A,B…). The same songs are not repeated.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _store_result(**kwargs):
    st.session_state["result"] = kwargs

def _key_norm(title: str, artist: str) -> str:
    return f"{(title or '').lower().strip()} — {(artist or '').lower().strip()}"

def _interleave_unique(list_a, list_b, limit=100):
    """A,B,A,B... sırayla; başlık+sanatçıya göre yinelenenleri at; limit kadar."""
    out, seen = [], set()
    for a, b in zip_longest(list_a, list_b, fillvalue=None):
        for e in (a, b):
            if not e:
                continue
            k = _key_norm(e.title, e.artist)
            if k in seen:
                continue
            out.append(e)
            seen.add(k)
            if len(out) >= limit:
                return out
    return out

# ---- İş akışı ----
if submitted:
    start = time.perf_counter()

    status = st.empty()
    bar = st.progress(0, text="Starting…")

    # --- Chart(lar)ı çek ---
    if not blend_mode:
        date1 = d1.strftime("%Y-%m-%d")
        status.write("Fetching Billboard Hot 100…")
        chart = fetch_hot100(date1)
        year = date1.split("-")[0]
        list_for_search = chart
        poster_date_text = date1
        default_name = f"{date1} Billboard Hot 100"
        subtitle = None
    else:
        date1 = d1.strftime("%Y-%m-%d")
        date2 = d2.strftime("%Y-%m-%d") if d2 else date1
        status.write("Fetching Billboard Hot 100 (two dates)…")
        chart1 = fetch_hot100(date1)
        chart2 = fetch_hot100(date2)
        list_for_search = _interleave_unique(chart1, chart2, limit=100)
        year = None  # blend: yıl filtreyi sıkı tutmayalım
        poster_date_text = f"{date1} × {date2}"
        default_name = f"Bestie Blend — {date1} × {date2}"
        subtitle = "Bestie Blend"

    # --- Spotify ---
    status.write("Connecting to Spotify…")
    sp = SpotifyClient(enable_cover_upload=upload_cover)

    # Eşleştirme
    uris, missing = [], []
    total = max(len(list_for_search), 1)
    for i, e in enumerate(list_for_search, start=1):
        yr = (year or (e.rank and ""))  # blend modda yıl yoksa boş geç
        uri = sp.search_best_track(e.title, e.artist, yr if yr else "")
        (uris if uri else missing).append(uri or e)
        pct = int(round(i * 100 / total))
        bar.progress(pct, text=f"Matching tracks… {i}/{total}")

    # Playlist oluştur / güncelle (aynı isimde varsa içerik REPLACE)
    status.write("Creating/updating playlist…")
    name = (custom_name or default_name).strip()
    desc = (f"Billboard Hot 100 - {poster_date_text}. Generated by hitcapsule."
            if not blend_mode else
            f"Bestie Blend — {poster_date_text}. Generated by hitcapsule.")
    pid, created_new = sp.upsert_playlist_with_items(
        name=name,
        public=make_public,
        description=desc,
        uris=[u for u in uris if isinstance(u, str)],
        replace=True  # aynı isimdeyse içeriği tamamen yenile
    )
    url = sp.get_playlist_url(pid)

    # Görseller
    status.write("Rendering poster/cover…")
    os.makedirs("artifacts", exist_ok=True)
    cover_path = os.path.join("artifacts", f"cover_{poster_date_text.replace(' ','_').replace(':','-')}.jpg")
    poster_path = os.path.join("artifacts", f"poster_{poster_date_text.replace(' ','_').replace(':','-')}.png")
    make_cover(poster_date_text, cover_path, playlist_name=name)
    # Poster: Top 10
    top10 = [(c.title, c.artist) for c in list_for_search[:10]]
    make_story_poster(poster_date_text, top10, url, poster_path, playlist_name=name, top_k=10, subtitle=subtitle)

    uploaded = False
    if upload_cover:
        uploaded = sp.upload_cover_image(pid, cover_path)

    duration = time.perf_counter() - start
    _store_result(
        date=poster_date_text, name=name, url=url,
        added=len([u for u in uris if isinstance(u, str)]),
        missing=len(missing), duration=duration,
        poster_path=poster_path, cover_path=cover_path, uploaded=uploaded,
        done=True, created_new=created_new
    )

    status.empty(); bar.empty()

# ---- Sağ kolon: Sekmeli sonuç kartı + poster önizleme ----
with right:
    res = st.session_state.get("result")
    if not res:
        st.markdown(
            '<div class="hc-card"><b>Ready when you are.</b><br>'
            '<span class="hc-muted">Pick a date and hit “Create My Playlist”.</span></div>',
            unsafe_allow_html=True,
        )
    else:
        tab_sum, tab_poster = st.tabs(["Summary", "Poster"])
        with tab_sum:
            badges = []
            if res.get("done"): badges.append("✅ Done")
            if res.get("uploaded"): badges.append("🟩 Cover uploaded")
            if res.get("created_new") is False: badges.append("♻️ Updated existing")
            if badges:
                st.markdown(
                    "<div class='hc-badge'>" + " &nbsp;•&nbsp; ".join(badges) + "</div>",
                    unsafe_allow_html=True,
                )

            st.subheader(res["name"])
            st.caption(f'Billboard Hot 100 — {res["date"]}')
            st.link_button("Open on Spotify", res["url"])

            m1, m2, m3 = st.columns(3)
            m1.metric("Added", res["added"])
            m2.metric("Missing", res["missing"])
            m3.metric("Time", f"{res['duration']:.1f}s")

        with tab_poster:
            PREVIEW_W = 180
            st.image(res["poster_path"], caption=f"Poster preview ({PREVIEW_W}px)", width=PREVIEW_W)
            with open(res["poster_path"], "rb") as f:
                st.download_button("Download poster.png", f, file_name=os.path.basename(res["poster_path"]))
            with st.expander("View full-size poster"):
                st.image(res["poster_path"], width="stretch")
