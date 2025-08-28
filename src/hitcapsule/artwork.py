from __future__ import annotations
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os

# Basit font fallback (özel TTF kullanmak istersen ./assets içine koy ve yolu değiştir)
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()

def make_cover(date_text: str, save_path: str) -> str:
    """640x640 kapak görseli üretir (JPG)."""
    W, H = 640, 640
    img = Image.new("RGB", (W, H), (28, 28, 28))
    d = ImageDraw.Draw(img)

    # Kenarlık kutusu
    d.rounded_rectangle((24, 24, W-24, H-24), radius=28, outline=(255, 255, 255), width=3)

    # Başlık
    title = "HitCapsule"
    date = date_text
    d.text((40, 60), title, font=_font(48), fill=(255, 255, 255))
    d.text((40, 120), date, font=_font(36), fill=(230, 230, 230))

    # Alt yazı
    d.text((40, H-90), "Billboard Hot 100", font=_font(24), fill=(200, 200, 200))
    d.text((40, H-60), "generated with hitcapsule", font=_font(18), fill=(160, 160, 160))

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    img.save(save_path, "JPEG", quality=92)
    return save_path

def make_story_poster(date_text: str, top5: List[Tuple[str, str]], playlist_url: str, save_path: str) -> str:
    """1080x1920 poster (PNG): tarih, top-5 ve QR kod."""
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(img)

    # Başlık
    d.text((60, 80), "HitCapsule", font=_font(72), fill=(255, 255, 255))
    d.text((60, 170), date_text, font=_font(54), fill=(230, 230, 230))
    d.text((60, 240), "Billboard Hot 100", font=_font(36), fill=(200, 200, 200))

    # Top 5
    y = 340
    for i, (title, artist) in enumerate(top5, start=1):
        d.text((60, y), f"{i}. {title}", font=_font(40), fill=(255, 255, 255))
        d.text((60, y+48), f"   {artist}", font=_font(28), fill=(200, 200, 200))
        y += 120

    # QR
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(playlist_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_w, qr_h = qr_img.size
    qr_target = 360
    qr_img = qr_img.resize((qr_target, qr_target))
    img.paste(qr_img, (W - qr_target - 60, H - qr_target - 60))

    d.text((60, H-100), "Scan to open on Spotify", font=_font(28), fill=(200, 200, 200))

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    img.save(save_path, "PNG")
    return save_path
