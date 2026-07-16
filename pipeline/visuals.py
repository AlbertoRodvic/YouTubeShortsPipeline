"""Image + video generation via the fal.ai queue API.

Results are cached by (model + prompt) hash next to the requested path, so
re-running a video only re-bills the visuals whose prompts changed.
"""
import base64
import os
import time
from pathlib import Path

import requests

from .util import download, sha


def _fal(model: str, payload: dict, timeout_s: int = 900) -> dict:
    key = os.environ.get("FAL_KEY", "")
    if not key:
        raise RuntimeError("FAL_KEY missing from .env")
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    r = requests.post(f"https://queue.fal.run/{model}", json=payload, headers=headers, timeout=60)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"fal submit error {r.status_code} for {model}: {r.text[:500]}")
    job = r.json()
    t0 = time.time()
    while True:
        s = requests.get(job["status_url"], headers=headers, timeout=30).json()
        status = s.get("status")
        if status == "COMPLETED":
            break
        if status not in ("IN_QUEUE", "IN_PROGRESS"):
            raise RuntimeError(f"fal job failed for {model}: {s}")
        if time.time() - t0 > timeout_s:
            raise RuntimeError(f"fal job timed out after {timeout_s}s for {model}")
        time.sleep(3)
    r = requests.get(job["response_url"], headers=headers, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"fal result error {r.status_code}: {r.text[:500]}")
    return r.json()


def gen_image(prompt: str, out: Path, cfg: dict, force=False) -> Path:
    model = cfg["fal"]["image_model"]
    cached = out.with_name(f"{out.stem}_{sha(model + prompt)}.png")
    if cached.exists() and not force:
        print(f"    cached: {cached.name}")
        return cached
    payload = dict(cfg["fal"].get("image_input") or {})
    payload["prompt"] = prompt
    payload.setdefault("num_images", 1)
    result = _fal(model, payload)
    download(result["images"][0]["url"], cached)
    return cached


def gen_video(prompt: str, out: Path, cfg: dict, force=False) -> Path:
    model = cfg["fal"]["video_model"]
    cached = out.with_name(f"{out.stem}_{sha(model + prompt)}.mp4")
    if cached.exists() and not force:
        print(f"    cached: {cached.name}")
        return cached
    payload = dict(cfg["fal"].get("video_input") or {})
    payload["prompt"] = prompt
    result = _fal(model, payload)
    download(result["video"]["url"], cached)
    return cached


def gen_i2v(prompt: str, image: Path, out: Path, cfg: dict, force=False) -> Path:
    """Animate a still with the image-to-video model (real AI motion instead of
    ffmpeg Ken Burns). Cached on (model + prompt + image content)."""
    model = cfg["fal"]["i2v_model"]
    img_bytes = image.read_bytes()
    cached = out.with_name(f"{out.stem}_{sha(model + prompt + sha(img_bytes.hex()))}.mp4")
    if cached.exists() and not force:
        print(f"    cached: {cached.name}")
        return cached
    payload = dict(cfg["fal"].get("i2v_input") or {})
    payload["prompt"] = prompt
    mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    payload["image_url"] = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
    result = _fal(model, payload)
    download(result["video"]["url"], cached)
    return cached


def placeholder_image(text: str, idx: int, out: Path, size=(1080, 1920)) -> Path:
    """Dry-run stand-in so assembly can be tested without any API spend."""
    from PIL import Image, ImageDraw, ImageFont

    colors = [(30, 40, 70), (60, 30, 50), (25, 60, 45), (70, 55, 25), (45, 30, 70)]
    img = Image.new("RGB", size, colors[idx % len(colors)])
    d = ImageDraw.Draw(img)
    try:
        big = ImageFont.truetype("arialbd.ttf", 220)
        small = ImageFont.truetype("arial.ttf", 42)
    except OSError:
        big = small = ImageFont.load_default()
    d.text((size[0] / 2, 700), f"SEG {idx + 1}", font=big, anchor="mm", fill=(255, 255, 255))
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) > 40:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    lines.append(line)
    for j, ln in enumerate(lines[:14]):
        d.text((size[0] / 2, 950 + j * 54), ln, font=small, anchor="mm", fill=(200, 200, 200))
    img.save(out)
    return out
