from __future__ import annotations
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os

# ---- Typo-safe font helper -------------------------------------------------
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try a system TTF; fall back to PIL default."""
    try:
        # Arial çoğu Windows'ta var; yoksa fallback'e düşer
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()

def _text_ellipsize(
    d: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int
) -> str:
    """Fit text into max_w with … using binary search."""
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

# Marka rengi: Spotify yeşili
BRAND = (29, 185, 84)
FG     = (255, 255, 255)
SUBFG  = (210, 210, 210)
MUTED  = (180, 180, 180)
BG     = (28, 28, 28)

# ---------------- COVER ----------------
def make_cover(
    date_text: str,
    save_path: str,
    playlist_name: Optional[str] = None,
) -> str:
    """640x640 kapak. Üstte playlist adı, altında tarih; sol altta etiketler."""
    W, H = 640, 640
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Çerçeve
    d.rounded_rectangle((24, 24, W - 24, H - 24), radius=28, outline=FG, width=3)

    # Üst başlıklar
    x0, y0 = 40, 56
    title_f = _font(52)
    date_f = _font(36)

    name = playlist_name or "HitCapsule"
    name = _text_ellipsize(d, name, title_f, W - x0 - 40)
    d.text((x0, y0), name, font=title_f, fill=FG)
    d.text((x0, y0 + 64), date_text, font=date_f, fill=SUBFG)

    # Sol alt etiketler
    base_y = H - 92
    d.text((40, base_y), "Billboard Hot 100", font=_font(24), fill=MUTED)

    # "generated with " + HitCapsule (renkli)
    gen = "generated with "
    gx = 40
    gy = H - 60
    d.text((gx, gy), gen, font=_font(18), fill=(160, 160, 160))
    gx += int(d.textlength(gen, font=_font(18)))
    d.text((gx, gy), "HitCapsule", font=_font(18), fill=BRAND)

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    img.save(save_path, "JPEG", quality=92)
    return save_path

# ---------------- POSTER ----------------
def make_story_poster(
    date_text: str,
    songs: List[Tuple[str, str]],
    playlist_url: str,
    save_path: str,
    playlist_name: Optional[str] = None,
    top_k: int = 10,
    subtitle: Optional[str] = None,
) -> str:
    """
    1080x1920 story posteri.
    Üstten aşağı: Playlist adı → (opsiyonel alt başlık) → Tarih → Top-N şarkı → sağ altta QR.
    Sol altta: Billboard Hot 100 + generated with HitCapsule.
    """
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Üst başlıklar
    x0, y0 = 60, 72
    name_f = _font(72)
    sub_f  = _font(34)
    date_f = _font(50)

    name = playlist_name or "HitCapsule"
    name = _text_ellipsize(d, name, name_f, W - x0 - 60)
    d.text((x0, y0), name, font=name_f, fill=FG)

    y = y0 + 78
    if subtitle:
        sub = _text_ellipsize(d, subtitle, sub_f, W - x0 - 60)
        d.text((x0, y), sub, font=sub_f, fill=(200, 200, 200))
        y += 44

    d.text((x0, y), date_text, font=date_f, fill=SUBFG)
    head_bottom = y + 64

    # Şarkı listesi
    list_start = head_bottom + 24
    row_h   = 96
    title_f = _font(40)
    artist_f = _font(26)

    # Sağ altta QR için güvenli alan
    qr_target = 360
    right_safe = qr_target + 100
    max_w = W - x0 - right_safe

    for i, (title, artist) in enumerate(songs[:top_k], start=1):
        yy = list_start + (i - 1) * row_h
        t = _text_ellipsize(d, f"{i}. {title}", title_f, max_w)
        a = _text_ellipsize(d, f"{artist}", artist_f, max_w)
        d.text((x0, yy), t, font=title_f, fill=FG)
        d.text((x0, yy + 42), a, font=artist_f, fill=MUTED)

    # QR + üstünde etiket (sağ altta)
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(playlist_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((qr_target, qr_target))

    qr_x = W - qr_target - 60
    qr_y = H - qr_target - 60
    # Etiket: QR'ın hemen üstünde ortalanmış
    label = "Scan to open on Spotify"
    label_f = _font(28)
    tw = int(d.textlength(label, font=label_f))
    lx = qr_x + (qr_target - tw) // 2
    ly = qr_y - 36
    d.text((lx, ly), label, font=label_f, fill=MUTED)

    img.paste(qr_img, (qr_x, qr_y))

    # Sol alt etiketler
    d.text((60, H - 92), "Billboard Hot 100", font=_font(24), fill=MUTED)
    gen = "generated with "
    gx = 60
    gy = H - 60
    d.text((gx, gy), gen, font=_font(18), fill=(160, 160, 160))
    gx += int(d.textlength(gen, font=_font(18)))
    d.text((gx, gy), "HitCapsule", font=_font(18), fill=BRAND)

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    img.save(save_path, "PNG")
    return save_path
