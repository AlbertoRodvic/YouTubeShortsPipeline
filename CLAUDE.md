# CLAUDE.md

Automated YouTube Shorts pipeline: the user writes a script (or just names a food/
topic), Claude turns it into a finished 9:16 video (ElevenLabs voice → fal.ai visuals
→ phrase-karaoke captions → corporate transitions + sfx → ffmpeg assembly → baked-in
thumbnail card). Faceless-channel format, cost-minimized (~$0.20/video: Flux schnell
images + one Seedance Lite hook clip).

## How work happens here

The primary interface is the `/make-video` skill (`.claude/skills/make-video/SKILL.md`)
— follow it whenever the user provides a script or asks for a video. Claude normalizes
the script, writes missing visual prompts, renders, QCs frames from the output, and
delivers the MP4. The user only writes scripts and uploads the result to YouTube.

## Commands

```
python -m pipeline.make_video scripts/<slug>.md    # full render
    --dry-run        # free: placeholder visuals + silent audio, tests everything local
    --sample         # preview: real images + voice, no paid hook clip (~$0.04)
    --no-hook-video  # same as --sample (legacy name)
    --regen N        # force-regenerate segment N's visual only
    --force          # ignore all caches
```

Output: `output/<slug>/<slug>.mp4` + `thumbnail.png` + `summary.json` (segment timings,
cost) + `qc/seg_NN.png` (auto-exported QC frames) + `metadata.txt` (upload info);
intermediates cached in `output/<slug>/work/` keyed by prompt hash — editing one
`visual:` prompt and re-running only re-bills that visual.

The pipeline is deterministic and self-contained (see README.md): it auto-appends the
standing style blocks to prompts, substitutes the script's `subject:` descriptor into
`{subject}` placeholders, and warns before billing if the narration misses the 61–70 s
target. Claude's job is writing good scripts and judging the QC frames, not plumbing.

## Layout

- `pipeline/` — parse_script, tts (ElevenLabs with-timestamps, one call per video),
  visuals (fal.ai queue API), captions (ASS karaoke), thumbnail, assemble (ffmpeg)
- `config.yaml` — voice id/settings, fal model ids, caption + thumbnail styling, prices
- `.env` — ELEVENLABS_API_KEY, FAL_KEY. Never print or echo these values.
- `scripts/` — canonical script markdowns (format spec in the skill; example:
  `scripts/buddhas-hand.md`)
- `assets/music/` — optional royalty-free tracks, auto-ducked under the voice
- `assets/sfx/` — optional sound design: `whoosh*` auto-plays into segment
  transitions, `impact*`/`hit*` on the hook at 0:00; empty folder = skipped

## Environment gotchas

- Windows / PowerShell 5.1; workspace path contains spaces (OneDrive) — always quote paths.
- ffmpeg is NOT on PATH: it's auto-detected from the winget install under
  `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*` by `pipeline/util.py:find_ffmpeg`.
- fal has no free tier — API calls fail at $0.00 balance. ElevenLabs free tier ≈ 10k
  chars/month (~10 videos) and requires ElevenLabs attribution in monetized videos.
- fal model ids drift; on a 422/schema error check https://fal.ai/models/<model-id>
  and fix `fal.*_input` payload keys in config.yaml.

## Conventions

- The user's narration is the product: keep it verbatim (encoding fixes only, ask the user before fixing typos);
  never rewrite it without asking.
- Default to the cheap models in config; discuss before switching to pricier ones.
  Visual tier (2026-07-15, user-approved): `video.image_motion: ai` — every still is
  animated with the Seedance image-to-video model (~$1.10–1.30/video). `kenburns` is
  the cheap fallback; `--sample`/`--dry-run` always use it.
- Channel format is a 6-beat documentary targeting 61–70 s (Shorts now allows up to 3 min;
  TikTok/Reels longer). Tune voice speed so it lands in range. Older 4-beat scripts are fine.
- Don't upload anywhere — the user reviews and uploads manually.
