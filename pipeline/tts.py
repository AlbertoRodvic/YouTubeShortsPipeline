"""ElevenLabs text-to-speech with character-level timestamps.

The whole narration goes out in ONE API call so the voice flows naturally
across segments; character spans then map the returned timing back onto
segments (for visual cut points) and words (for karaoke captions).
"""
import base64
import os
import re
from pathlib import Path

import requests

from .util import media_duration, read_json, run, sha, write_json


def _spans(narrations):
    spans, pos, parts = [], 0, []
    for n in narrations:
        parts.append(n)
        spans.append((pos, pos + len(n)))
        pos += len(n) + 1  # the joining space
    return " ".join(parts), spans


def synthesize(narrations, cfg, work: Path, dry_run=False, ffmpeg="ffmpeg"):
    text, spans = _spans(narrations)
    if dry_run:
        return _dry_run(text, spans, work, ffmpeg)

    el = cfg["elevenlabs"]
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY missing from .env")
    if not el.get("voice_id"):
        raise RuntimeError("elevenlabs.voice_id is empty in config.yaml")

    key = sha(text + el["voice_id"] + str(el.get("voice_settings")))
    mp3, meta = work / f"tts_{key}.mp3", work / f"tts_{key}.json"
    if mp3.exists() and meta.exists():
        print("  TTS: cached")
        data = read_json(meta)
    else:
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{el['voice_id']}/with-timestamps"
            f"?output_format={el.get('output_format', 'mp3_44100_128')}"
        )
        resp = requests.post(
            url,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": el.get("model_id", "eleven_multilingual_v2"),
                "voice_settings": el.get("voice_settings", {}),
            },
            timeout=300,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        mp3.write_bytes(base64.b64decode(data["audio_base64"]))
        data.pop("audio_base64", None)
        write_json(meta, data)

    align = data["alignment"]
    starts = align["character_start_times_seconds"]
    ends = align["character_end_times_seconds"]
    n = min(len(starts), len(ends), len(text))
    duration = media_duration(mp3, ffmpeg)
    seg_times = _segment_times(spans, starts, n, duration)
    words = _word_times(text, starts, ends, n)
    return {"audio": mp3, "duration": duration, "segments": seg_times, "words": words, "chars": len(text)}


def _segment_times(spans, starts, n, duration):
    """Segment i runs from its first character's start time to segment i+1's
    start (pauses belong to the preceding visual); the last runs to the end."""
    bounds = [starts[min(s, n - 1)] if n else 0.0 for s, _ in spans]
    times = []
    for i, b in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else duration
        times.append({"start": round(b, 3), "end": round(end, 3)})
    if times:
        times[0]["start"] = 0.0
    return times


def _word_times(text, starts, ends, n):
    words = []
    for m in re.finditer(r"\S+", text):
        a, b = m.start(), m.end() - 1
        if a >= n:
            break
        words.append({
            "text": m.group(),
            "start": round(starts[a], 3),
            "end": round(ends[min(b, n - 1)], 3),
        })
    return words


def _dry_run(text, spans, work: Path, ffmpeg):
    """No API call: silent audio + evenly spaced word timings at ~2.6 words/s."""
    rate = 2.6
    tokens = [(m.group(), m.start()) for m in re.finditer(r"\S+", text)]
    step = 1.0 / rate
    words, char_time, t = [], {}, 0.0
    for w, a in tokens:
        words.append({"text": w, "start": round(t, 3), "end": round(t + step * 0.85, 3)})
        char_time[a] = t
        t += step
    duration = round(t, 3)
    mp3 = work / "tts_dryrun.mp3"
    run([ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{duration}", "-q:a", "9", mp3])
    bounds = [next((char_time[a] for _, a in tokens if a >= s), 0.0) for s, _ in spans]
    seg_times = []
    for i, b in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else duration
        seg_times.append({"start": round(b, 3), "end": round(end, 3)})
    if seg_times:
        seg_times[0]["start"] = 0.0
    return {"audio": mp3, "duration": duration, "segments": seg_times, "words": words, "chars": len(text)}
