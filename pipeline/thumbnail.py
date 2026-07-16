"""Compose the thumbnail title card: hook image + big stroked title text.

YouTube Shorts can't take a custom thumbnail upload, so this card is also baked
into the video itself (first or last frames, per config) where YouTube's frame
picker can grab it. The PNG is saved alongside the MP4 for reference.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont


def _font(size: int):
    for name in ("ariblk.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_thumbnail(base_img: Path, text: str, out: Path, cfg: dict) -> Path:
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    th = cfg.get("thumbnail", {})

    img = Image.open(base_img).convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)))
    x0, y0 = (img.width - W) // 2, (img.height - H) // 2
    img = img.crop((x0, y0, x0 + W, y0 + H))
    img = ImageEnhance.Brightness(img).enhance(0.82)  # dim slightly for text contrast

    size = int(th.get("font_size", 130))
    font = _font(size)
    d = ImageDraw.Draw(img)
    words = (text.upper() if th.get("uppercase", True) else text).split()
    lines, line = [], ""
    max_w = W - 140
    for w in words:
        trial = (line + " " + w).strip()
        if line and d.textlength(trial, font=font) > max_w:
            lines.append(line)
            line = w
        else:
            line = trial
    lines.append(line)

    lh = int(size * 1.18)
    y = int(H * float(th.get("y_center_frac", 0.42))) - lh * (len(lines) - 1) // 2
    stroke = max(4, size // 12)
    for ln in lines:
        d.text((W // 2, y), ln, font=font, anchor="mm", fill=(255, 255, 255),
               stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += lh
    img.save(out)
    return out
