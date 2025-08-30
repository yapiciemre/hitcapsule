from __future__ import annotations
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os

# ————— Font (basit fallback) —————
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()

# ————— Yardımcılar —————
def _text_ellipsize(d: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> str:
    if d.textlength(text, font=font) <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        t = text[:mid] + "…"
        if d.textlength(t, font=font) <= max_w:
            lo = mid + 1
        else:
            hi = mid
    return (text[:max(lo - 1, 0)] + "…") if text else ""

# ————— COVER 640x640 —————
def make_cover(date_text: str, save_path: str, playlist_name: Optional[str] = None) -> str:
    """Kapak: 640x640, koyu zemin, büyük tarih, opsiyonel playlist adı."""
    W, H = 640, 640
    img = Image.new("RGB", (W, H), (28, 28, 28))
    d = ImageDraw.Draw(img)

    # Kenarlık
    d.rounded_rectangle((24, 24, W-24, H-24), radius=28, outline=(255, 255, 255), width=3)

    # Üst sol
    d.text((40, 60), "HitCapsule", font=_font(48), fill=(255, 255, 255))
    d.text((40, 120), date_text,     font=_font(36), fill=(230, 230, 230))

    # Playlist adı (varsa)
    if playlist_name:
        d.text((40, 168), f"Playlist: {playlist_name}", font=_font(24), fill=(210, 210, 210))

    # Alt sol
    d.text((40, H-90), "Billboard Hot 100",       font=_font(24), fill=(200, 200, 200))
    d.text((40, H-60), "generated with hitcapsule", font=_font(18), fill=(160, 160, 160))

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    img.save(save_path, "JPEG", quality=92)
    return save_path

# ————— POSTER 1080x1920 —————
def make_story_poster(
    date_text: str,
    songs: List[Tuple[str, str]],
    playlist_url: str,
    save_path: str,
    playlist_name: Optional[str] = None,
    top_k: int = 8,
) -> str:
    """
    Poster: 1080x1920, başlık+ tarih + Billboard, ilk N şarkı (default 8) + QR.
    - Uzun başlık/sanatçı isimleri tek satıra sığdırılır (ellipsis).
    - Sağ alttaki QR için güvenli alan ayrılır.
    """
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(img)

    # Başlık bloğu
    x0 = 60
    d.text((x0, 80),  "HitCapsule",        font=_font(72), fill=(255, 255, 255))
    d.text((x0, 170), date_text,           font=_font(54), fill=(230, 230, 230))
    d.text((x0, 240), "Billboard Hot 100", font=_font(36), fill=(200, 200, 200))
    if playlist_name:
        d.text((x0, 290), f"Playlist: {playlist_name}", font=_font(32), fill=(210, 210, 210))

    # Liste alanı
    list_start_y = 340 if not playlist_name else 380
    row_h        = 110  # 8 şarkı için uygun satır yüksekliği
    title_f      = _font(42)
    artist_f     = _font(28)

    # Sağ altta QR için güvenli alan bırak (genişliği azalt)
    qr_target = 360
    right_safe = qr_target + 100  # sağdan güvenli alan
    max_w = W - x0 - right_safe

    # İlk N şarkı
    for i, (title, artist) in enumerate(songs[:top_k], start=1):
        y = list_start_y + (i-1) * row_h
        t = _text_ellipsize(d, f"{i}. {title}", title_f, max_w)
        a = _text_ellipsize(d, f"{artist}",    artist_f, max_w)
        d.text((x0, y),   t, font=title_f,  fill=(255, 255, 255))
        d.text((x0, y+44), a, font=artist_f, fill=(200, 200, 200))

    # QR
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(playlist_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((qr_target, qr_target))

    qr_x = W - qr_target - 60
    qr_y = H - qr_target - 60
    img.paste(qr_img, (qr_x, qr_y))

    # Alt sol bilgilendirme
    d.text((60, H-100), "Scan to open on Spotify", font=_font(28), fill=(200, 200, 200))

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    img.save(save_path, "PNG")
    return save_path
