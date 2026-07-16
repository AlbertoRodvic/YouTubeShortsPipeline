import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

load_dotenv(ROOT / ".env")


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sha(text: str, n: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def find_ffmpeg(cfg: dict) -> str:
    candidates = []
    explicit = (cfg.get("paths") or {}).get("ffmpeg") or ""
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(Path(found))
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates.append(Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe")
        candidates.append(Path(local) / "Tools" / "ffmpeg" / "bin" / "ffmpeg.exe")
        pkgs = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if pkgs.exists():
            candidates.extend(sorted(pkgs.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"), reverse=True))
    for c in candidates:
        if c.exists():
            return str(c)
    raise RuntimeError(
        "ffmpeg not found. Install it (winget install Gyan.FFmpeg) or set paths.ffmpeg in config.yaml."
    )


def ffprobe_path(ffmpeg: str) -> str:
    p = Path(ffmpeg)
    probe = p.with_name("ffprobe" + p.suffix)
    return str(probe) if probe.exists() else "ffprobe"


def run(cmd: list, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-3000:]
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd[0]}\n{tail}")
    return proc.stdout


def media_duration(path, ffmpeg: str) -> float:
    out = run([
        ffprobe_path(ffmpeg), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return float(out.strip())


def download(url: str, path: Path) -> None:
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    path.write_bytes(r.content)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
