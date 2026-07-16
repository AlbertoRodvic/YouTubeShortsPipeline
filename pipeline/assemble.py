"""ffmpeg assembly: per-segment clips -> corporate transitions -> captions + audio/sfx mux.

Transitions are xfade-based (smooth slides / pushes / zooms / wipes, cycled from
config `transitions.types`). Each clip except the last is padded with a clone of
its final frame for the transition duration, so every segment still starts at
its original narration timestamp and voice/caption sync is preserved.

Sound design: optional files in assets/sfx/ are mixed in automatically —
`whoosh*` swells into every segment change, `impact*` (or `hit*`) lands on the
hook at 0:00. The folder being empty just skips sound design.
"""
from pathlib import Path

from .util import ROOT, media_duration, run


def _kb_preset(idx: int, frames: int):
    """Ken Burns presets cycled across image segments: (zoom, x, y) expressions."""
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    n = max(frames - 1, 1)
    presets = [
        (f"1+0.12*on/{n}", cx, cy),                    # slow zoom in
        (f"1.12-0.12*on/{n}", cx, cy),                 # slow zoom out
        ("1.10", f"(iw-iw/zoom)*on/{n}", cy),          # pan right
        ("1.10", f"(iw-iw/zoom)*(1-on/{n})", cy),      # pan left
        ("1.10", cx, f"(ih-ih/zoom)*on/{n}"),          # pan down
    ]
    return presets[idx % len(presets)]


def image_clip(img: Path, dur: float, idx: int, out: Path, cfg: dict, ffmpeg: str):
    v = cfg["video"]
    fps = v.get("fps", 30)
    frames = max(int(round(dur * fps)), 1)
    z, x, y = _kb_preset(idx, frames)
    # upscale 2x before zoompan to avoid the filter's integer-rounding jitter
    w2, h2 = v["width"] * 2, v["height"] * 2
    vf = (
        f"scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={v['width']}x{v['height']}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )
    run([ffmpeg, "-y", "-loop", "1", "-i", img, "-vf", vf, "-frames:v", frames,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])


def still_clip(img: Path, dur: float, out: Path, cfg: dict, ffmpeg: str):
    """Static hold of one image (used for the baked-in thumbnail card)."""
    v = cfg["video"]
    fps = v.get("fps", 30)
    vf = (
        f"scale={v['width']}:{v['height']}:force_original_aspect_ratio=increase,"
        f"crop={v['width']}:{v['height']},fps={fps},setsar=1,format=yuv420p"
    )
    run([ffmpeg, "-y", "-loop", "1", "-t", f"{dur:.3f}", "-i", img, "-vf", vf,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])


def video_clip(src: Path, dur: float, out: Path, cfg: dict, ffmpeg: str):
    """Fit an AI-generated clip to the segment duration: trim if long, slow down
    to cover if short. Large slowdowns are motion-interpolated back to full fps
    so motion stays fluid. A clip NEVER freezes on its last frame."""
    v = cfg["video"]
    fps = v.get("fps", 30)
    src_dur = media_duration(src, ffmpeg)
    base = (
        f"scale={v['width']}:{v['height']}:force_original_aspect_ratio=increase,"
        f"crop={v['width']}:{v['height']},setsar=1,format=yuv420p"
    )
    if src_dur + 0.05 >= dur:
        vf = f"fps={fps}," + base
    else:
        r = dur / src_dur
        vf = f"setpts={r:.5f}*PTS,"
        if r > 1.25:
            # interpolate at source resolution (cheaper), then scale up
            vf += f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1,"
        else:
            vf += f"fps={fps},"
        vf += base
    run([ffmpeg, "-y", "-i", src, "-vf", vf, "-t", f"{dur:.3f}", "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])


def _find_sfx(stem: str):
    d = ROOT / "assets" / "sfx"
    if not d.exists():
        return None
    for p in sorted(d.glob(f"{stem}*")):
        if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac", ".ogg"):
            return p
    return None


def _transition_video(clips, durs, starts, silent: Path, work: Path, cfg: dict, ffmpeg: str):
    """Join clips with corporate xfade transitions into one silent video.

    Clip i is tpad-cloned by its transition duration so the crossfade eats the
    frozen tail, not the next segment's opening — segment start times (and thus
    voice/caption sync) are unchanged. Very short clips (the 0.2 s thumbnail
    card) fall back to a near-cut micro-fade.
    """
    tr = cfg.get("transitions") or {}
    tdur = float(tr.get("duration", 0.35))
    types = tr.get("types") or ["fade", "smoothleft", "smoothright", "zoomin", "wipeup"]
    n = len(clips)
    pair_t = [min(tdur, durs[i] * 0.45, durs[i + 1] * 0.45) for i in range(n - 1)]

    fc, pads = [], []
    for i in range(n):
        if i < n - 1:
            fc.append(f"[{i}:v]tpad=stop_mode=clone:stop_duration={pair_t[i]:.3f}[p{i}]")
            pads.append(f"[p{i}]")
        else:
            pads.append(f"[{i}:v]")
    cur = pads[0]
    for k in range(1, n):
        t = pair_t[k - 1]
        ttype = types[(k - 1) % len(types)] if t >= 0.15 else "fade"
        nxt = f"[x{k}]"
        fc.append(f"{cur}{pads[k]}xfade=transition={ttype}:duration={t:.3f}:offset={starts[k]:.3f}{nxt}")
        cur = nxt
    fc.append(f"{cur}format=yuv420p[v]")

    cmd = [ffmpeg, "-y"]
    for c in clips:
        cmd += ["-i", c.name]
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", silent.name]
    run(cmd, cwd=work)


def assemble(clips, voice: Path, ass_name, out: Path, work: Path, cfg: dict, ffmpeg: str, music,
             audio_offset: float = 0.0):
    """audio_offset delays the voice (and captions were shifted to match) when a
    thumbnail card is prepended to the video."""
    durs = [media_duration(c, ffmpeg) for c in clips]
    starts = [round(sum(durs[:i]), 3) for i in range(len(clips))]

    tr = cfg.get("transitions") or {}
    silent = work / "video_noaudio.mp4"
    if bool(tr.get("enabled", True)) and len(clips) > 1:
        print(f"  transitions: {len(clips) - 1} corporate xfades")
        _transition_video(clips, durs, starts, silent, work, cfg, ffmpeg)
    else:
        lst = work / "concat.txt"
        lst.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", silent.name], cwd=work)

    sfx_cfg = cfg.get("sfx") or {}
    sfx_on = bool(sfx_cfg.get("enabled", True))
    boundaries = [b for b in starts[1:] if b >= 1.0]  # skip the thumbnail-card cut
    whoosh = _find_sfx("whoosh") if sfx_on else None
    impact = (_find_sfx("impact") or _find_sfx("hit")) if sfx_on else None
    if sfx_on and (whoosh or impact):
        found = ", ".join(p.name for p in (whoosh, impact) if p)
        print(f"  sfx: {found}")

    vf = f"subtitles={ass_name}" if ass_name else "null"
    ms = int(round(audio_offset * 1000))
    delay = f"adelay={ms}:all=1" if ms > 0 else "anull"
    cmd = [ffmpeg, "-y", "-i", silent.name, "-i", str(voice)]
    idx = 2
    music_idx = whoosh_idx = impact_idx = None
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        music_idx, idx = idx, idx + 1
    if whoosh and boundaries:
        cmd += ["-i", str(whoosh)]
        whoosh_idx, idx = idx, idx + 1
    if impact:
        cmd += ["-i", str(impact)]
        impact_idx, idx = idx, idx + 1

    parts = [f"[0:v]{vf}[v]"]
    mix = []  # voice chain must stay first: amix duration=first keys off it
    if music_idx is not None:
        vol = cfg["music"].get("volume_db", -22)
        parts.append(f"[{music_idx}:a]volume={vol}dB[m]")
        if cfg["music"].get("duck", True):
            parts.append(f"[1:a]{delay},asplit=2[vc1][vc2]")
            parts.append(f"[m][vc1]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=400[duck]")
            mix = ["[vc2]", "[duck]"]
        else:
            parts.append(f"[1:a]{delay}[vc]")
            mix = ["[vc]", "[m]"]
    else:
        parts.append(f"[1:a]{delay}[vc]")
        mix = ["[vc]"]

    sfx_db = sfx_cfg.get("volume_db", -12)
    lead = float(sfx_cfg.get("whoosh_lead", 0.25))
    if whoosh_idx is not None:
        k = len(boundaries)
        if k == 1:
            parts.append(f"[{whoosh_idx}:a]volume={sfx_db}dB[w0]")
        else:
            outs = "".join(f"[w{j}]" for j in range(k))
            parts.append(f"[{whoosh_idx}:a]volume={sfx_db}dB,asplit={k}{outs}")
        for j, b in enumerate(boundaries):
            wms = max(0, int(round((b - lead) * 1000)))
            parts.append(f"[w{j}]adelay={wms}:all=1[sw{j}]")
            mix.append(f"[sw{j}]")
    if impact_idx is not None:
        parts.append(f"[{impact_idx}:a]volume={sfx_db}dB[imp]")
        mix.append("[imp]")

    if len(mix) == 1:
        amap = mix[0]
    else:
        parts.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0[a]")
        amap = "[a]"

    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", amap,
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    run(cmd, cwd=work)
