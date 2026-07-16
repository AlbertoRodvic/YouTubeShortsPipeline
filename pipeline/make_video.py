"""Script -> finished 9:16 short.

Usage:
    python -m pipeline.make_video scripts/<name>.md [flags]

Flags:
    --dry-run         no API calls: placeholder visuals + silent audio (free structural test)
    --sample          preview build: real images + voice but NO paid hook video clip
    --no-voice        skip ElevenLabs only: silent audio + estimated timings, real visuals
    --no-hook-video   same as --sample (legacy name)
    --regen N         force regeneration of segment N's visual (repeatable, 1-based)
    --force           ignore all caches

Deterministic pipeline behaviors (no operator judgement needed):
    - the standing camera-motion + human-POV style is auto-appended to every
      `type: video` prompt (config video.video_style_suffix); the still-quality
      style to every image prompt (video.image_style_suffix)
    - narration length is checked against the target duration before spending
      API credits (config video.target_seconds)
    - after rendering, one QC frame per segment is exported to output/<slug>/qc/
      — eyeball them; to fix a segment edit its `visual:` and re-run --regen N
    - output/<slug>/metadata.txt gets a ready-to-paste YouTube description
"""
import argparse
from pathlib import Path

from .util import media_duration, run

from . import visuals
from .assemble import assemble, image_clip, still_clip, video_clip
from .captions import build_ass
from .parse_script import parse_script
from .thumbnail import build_thumbnail
from .tts import synthesize
from .util import ROOT, find_ffmpeg, load_config, write_json


def main():
    ap = argparse.ArgumentParser(description="Script -> finished 9:16 short")
    ap.add_argument("script")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", action="store_true",
                    help="preview: real images + voice, no paid hook video clip")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--no-hook-video", action="store_true")
    ap.add_argument("--regen", type=int, action="append", default=[])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.sample:
        args.no_hook_video = True

    cfg = load_config()
    ffmpeg = find_ffmpeg(cfg)
    doc = parse_script(Path(args.script))
    slug = doc["slug"]
    out_dir = ROOT / "output" / slug
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    for w in doc["warnings"]:
        print(f"  WARNING: {w}")

    # Narration length guard: catch too-short/too-long scripts BEFORE spending credits.
    # ~0.0627 s/char at speed 1.0 (measured); scaled by the configured voice speed.
    speed = float((cfg["elevenlabs"].get("voice_settings") or {}).get("speed") or 1.0)
    n_chars = sum(len(s["narration"]) for s in doc["segments"]) + max(len(doc["segments"]) - 1, 0)
    est = n_chars * 0.0627 / speed
    lo, hi = (cfg["video"].get("target_seconds") or [61, 70])[:2]
    print(f"  narration: {n_chars} chars ~ {est:.0f}s at voice speed {speed} (target {lo}-{hi}s)")
    if not lo <= est <= hi:
        print("  WARNING: estimated duration outside target - lengthen/shorten the narration "
              "or adjust elevenlabs.voice_settings.speed")

    print(f"[1/4] Voice ({len(doc['segments'])} segments)")
    tts = synthesize([s["narration"] for s in doc["segments"]], cfg, work,
                     dry_run=args.dry_run or args.no_voice, ffmpeg=ffmpeg)

    print("[2/4] Visuals")
    clips = []
    seg_images = {}  # segment index -> rendered image path (image segments only)
    kinds = []
    n_images = n_videos = 0
    video_secs = 0.0
    # AI motion: animate each still with the image-to-video model. --sample and
    # --dry-run stay on free Ken Burns so previews remain cheap.
    ai_planned = (cfg["video"].get("image_motion", "kenburns") == "ai"
                  and not args.no_hook_video)
    ai_motion = ai_planned and not args.dry_run
    i2v_secs = float((cfg["fal"].get("i2v_input") or {}).get("duration", 5)) if ai_planned else 0.0
    for i, (seg, t) in enumerate(zip(doc["segments"], tts["segments"])):
        dur = max(t["end"] - t["start"], 0.5)
        kind = (seg.get("type") or "").lower()
        if not kind:
            kind = "video" if (i == 0 and cfg["video"].get("hybrid_hook", True)) else "image"
        if args.no_hook_video:
            kind = "image"
        # cost estimate reflects the planned kind even when dry-run demotes it
        if kind == "video":
            n_videos += 1
            video_secs += float(cfg["fal"]["video_input"].get("duration", 5))
        else:
            n_images += 1
            video_secs += i2v_secs  # 0 unless AI motion is planned
        if args.dry_run:
            kind = "image"
        kinds.append(kind)
        force = args.force or (i + 1) in args.regen
        clip = work / f"clip_{i:02d}.mp4"
        if kind == "video":
            print(f"  seg {i + 1}: AI video, {dur:.1f}s")
            prompt = seg["visual"]
            # auto-append the standing motion+POV style unless the prompt already carries it
            vsuffix = cfg["video"].get("video_style_suffix", "")
            if vsuffix and "go forward, parallax" not in prompt:
                prompt += vsuffix
            src = visuals.gen_video(prompt, work / f"seg{i:02d}_video.mp4", cfg, force=force)
            video_clip(src, dur, clip, cfg, ffmpeg)
        else:
            if args.dry_run:
                print(f"  seg {i + 1}: image, {dur:.1f}s")
                img = work / f"seg{i:02d}_placeholder.png"
                visuals.placeholder_image(seg["visual"], i, img)
            else:
                prompt = seg["visual"] + cfg["video"].get("image_style_suffix", "")
                img = visuals.gen_image(prompt, work / f"seg{i:02d}_img.png", cfg, force=force)
            if ai_motion and not args.dry_run:
                print(f"  seg {i + 1}: image + AI motion, {dur:.1f}s")
                src = visuals.gen_i2v(cfg["video"].get("i2v_motion_prompt", ""), img,
                                      work / f"seg{i:02d}_i2v.mp4", cfg, force=force)
                video_clip(src, dur, clip, cfg, ffmpeg)
            else:
                if not args.dry_run:
                    print(f"  seg {i + 1}: image, {dur:.1f}s")
                image_clip(img, dur, i, clip, cfg, ffmpeg)
            seg_images[i] = img
        clips.append(clip)

    # Thumbnail card: composed from the hook image, baked into the video where
    # YouTube's Shorts frame picker can select it, and exported as a PNG.
    thumb_cfg = cfg.get("thumbnail", {})
    thumb_png = None
    offset = 0.0
    if thumb_cfg.get("enabled", True):
        if 0 in seg_images:
            src_img = seg_images[0]
        else:  # hook is an AI video; generate a matching still for the card
            prompt = doc["segments"][0]["visual"] + cfg["video"].get("image_style_suffix", "")
            src_img = visuals.gen_image(prompt, work / "seg00_img.png", cfg,
                                        force=args.force or 1 in args.regen)
            n_images += 1
        thumb_png = out_dir / "thumbnail.png"
        build_thumbnail(src_img, doc["thumbnail_text"], thumb_png, cfg)
        tclip = work / "clip_thumb.mp4"
        tsec = float(thumb_cfg.get("seconds", 0.2))
        still_clip(thumb_png, tsec, tclip, cfg, ffmpeg)
        if thumb_cfg.get("mode", "first") == "last":
            clips.append(tclip)
        else:
            clips.insert(0, tclip)
            offset = tsec
        print(f"  thumbnail: {thumb_cfg.get('mode', 'first')} {tsec}s -> {thumb_png.name}")

    print("[3/4] Captions")
    ass_name = None
    if cfg["captions"].get("enabled", True):
        tr_cfg = cfg.get("transitions") or {}
        # keep the card clean: no captions/title until it has fully transitioned out
        min_start = offset + (float(tr_cfg.get("duration", 0.35))
                              if tr_cfg.get("enabled", True) else 0.0) if offset else 0.0
        (work / "captions.ass").write_text(
            build_ass(tts["words"], doc["segments"], tts["segments"], cfg, offset=offset,
                      title_text=doc["thumbnail_text"] if thumb_cfg.get("enabled", True) else "",
                      min_start=min_start),
            encoding="utf-8")
        ass_name = "captions.ass"

    music = None
    if cfg["music"].get("enabled", True):
        mdir = ROOT / "assets" / "music"
        tracks = sorted(p for p in mdir.glob("*")
                        if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac")) if mdir.exists() else []
        if tracks:
            music = tracks[sum(map(ord, slug)) % len(tracks)]
            print(f"  music: {music.name}")

    print("[4/4] Assemble")
    final = out_dir / f"{slug}.mp4"
    assemble(clips, tts["audio"], ass_name, final, work, cfg, ffmpeg, music, audio_offset=offset)

    # Automatic QC: one frame per segment midpoint. Check each for: visual matches
    # the beat, food looks identical across frames, captions readable. Fix a bad
    # segment by editing its `visual:` in the script and re-running with --regen N.
    qc_dir = out_dir / "qc"
    qc_dir.mkdir(exist_ok=True)
    total = media_duration(final, ffmpeg)
    for i, t in enumerate(tts["segments"]):
        mid = min((t["start"] + t["end"]) / 2 + offset, max(total - 0.1, 0))
        run([ffmpeg, "-y", "-ss", f"{mid:.2f}", "-i", final, "-frames:v", "1",
             qc_dir / f"seg_{i + 1:02d}.png"])
    print(f"  QC frames: {qc_dir}")

    prices = cfg.get("prices", {})
    cost = (n_images * prices.get("image", 0)
            + video_secs * prices.get("video_per_second", 0)
            + tts["chars"] / 1000 * prices.get("elevenlabs_per_1k_chars", 0))
    write_json(out_dir / "summary.json", {
        "title": doc["title"],
        "output": str(final),
        "thumbnail": str(thumb_png) if thumb_png else None,
        "duration_s": round(tts["duration"] + offset, 2),
        "segments": [  # in final-video time (shifted if a thumbnail card leads)
            {"label": s["label"], "start": round(t["start"] + offset, 3), "end": round(t["end"] + offset, 3)}
            for s, t in zip(doc["segments"], tts["segments"])
        ],
        "tts_characters": tts["chars"],
        "images": n_images,
        "video_clips": n_videos,
        "estimated_api_cost_usd": round(cost, 3),
        "dry_run": args.dry_run,
    })
    meta_cfg = cfg.get("metadata") or {}
    hook = doc["segments"][0]["narration"]
    (out_dir / "metadata.txt").write_text(
        f"Title: {doc['title']}\n"
        f"Thumbnail text: {doc['thumbnail_text']}\n"
        f"Duration: {tts['duration'] + offset:.1f}s"
        f"{'  (SAMPLE - no hook video)' if args.no_hook_video else ''}\n\n"
        f"Suggested description:\n{hook}\n"
        f"{meta_cfg.get('attribution', 'Narration voice created with ElevenLabs.')}\n\n"
        f"Hashtags: {meta_cfg.get('hashtags', '#shorts #food #foodfacts #documentary')}\n\n"
        f"--- Narration ---\n"
        + "".join(f"[{i + 1}] {s['label']}: {s['narration']}\n"
                  for i, s in enumerate(doc["segments"])),
        encoding="utf-8")

    print(f"\nDone: {final}")
    print(f"Duration {tts['duration']:.1f}s | est. cost ${cost:.2f} + {tts['chars']} ElevenLabs chars")
    print(f"Upload info: {out_dir / 'metadata.txt'}")


if __name__ == "__main__":
    main()
