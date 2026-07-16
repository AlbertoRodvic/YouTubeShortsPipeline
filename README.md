# AI Shorts Pipeline

Turns a markdown script into a finished 9:16 viral food-documentary Short:
ElevenLabs voice → fal.ai visuals → phrase-karaoke captions → corporate
transitions + sound design → ffmpeg assembly → baked-in thumbnail card.

Runs fully standalone from the CLI — no AI assistant needed to operate it.

## One-time setup

1. Python 3.10+, then `pip install -r requirements.txt`
2. ffmpeg: `winget install Gyan.FFmpeg` (auto-detected; or set `paths.ffmpeg` in config.yaml)
3. Copy `.env.example` to `.env` and paste in `ELEVENLABS_API_KEY` and `FAL_KEY`. Never share it.
4. Optional: drop royalty-free mp3/wav into `assets/music/` (auto-ducked bed) and
   `assets/sfx/` (`whoosh*` plays into every transition, `impact*`/`hit*` on the hook at 0:00).

## Workflow

```
python -m pipeline.make_video scripts/my-food.md --dry-run   # 1. FREE structural test
python -m pipeline.make_video scripts/my-food.md --sample    # 2. preview: images + voice, NO hook video (~$0.04)
python -m pipeline.make_video scripts/my-food.md             # 3. full render (adds the hook clip, ~$0.18 more)
python -m pipeline.make_video scripts/my-food.md --regen 3   # 4. redo only segment 3's visual (~$0.006)
```

Always sample before the full render. Everything is cached by prompt hash in
`output/<slug>/work/` — a re-run only re-bills visuals whose `visual:` text
changed, so steps 2→3 never pay twice for the same image or voice line.

After every render:

- **`output/<slug>/qc/seg_NN.png`** — one frame per segment, exported
  automatically. Check: visual matches the beat, the food looks IDENTICAL in
  every frame, captions readable. Fix a bad segment by editing its `visual:`
  line and re-running; use `--regen N` to force one whose prompt didn't change.
- **`output/<slug>/metadata.txt`** — ready-to-paste YouTube title, description
  (with the required ElevenLabs attribution) and hashtags.
- **`output/<slug>/thumbnail.png`** — the title card baked into the first 0.2 s
  (Shorts can't upload custom thumbnails; YouTube's frame picker can grab it).

Upload manually — nothing in this repo publishes anywhere.

## Script format (`scripts/<name>.md`)

```markdown
# The Blueberry That Isn't Blue
thumbnail: THE PINK BLUEBERRY
subject: small round vivid hot pink berries, every single berry the same bright magenta-pink color with a small star-shaped crown

## Hook
overlay: THIS IS A REAL BLUEBERRY
visual: A dramatic macro cinematic shot of a cluster of {subject}, hanging from a leafy branch, morning dew, golden sunlight
narration: This is not a raspberry. And no, it is not unripe...

## Introduction
visual: A garden bush covered in {subject}, warm afternoon light, professional nature photography
narration: ...
```

Rules that make it work (learned the hard way):

- **6 beats**, ~10–12 s each: Hook → Introduction → Unique feature → Origin →
  Experience → Final wow (end on a question inviting comments). The renderer
  estimates the duration from the narration and warns before billing if it
  misses the 61–70 s target — lengthen/shorten the text or tune
  `elevenlabs.voice_settings.speed`.
- **`subject:` + `{subject}`** — write the food's exact look ONCE and reference
  it in every visual; the parser substitutes it verbatim so the food doesn't
  change appearance between clips. The renderer warns about visuals that skip it.
- **Color traps:** in crowded shots, naming the real fruit ("blueberries")
  drags the model toward its real color. Describe the shape + the color you
  want ("small round vivid hot pink berries"), not the fruit name.
- **Avoid in visuals:** text-in-image, hands doing precise actions, multi-person
  scenes — image models fail at these. One clear subject per shot.
- **`overlay:`** renders as an animated lower-third fact card ("ORIGIN: USDA,
  1991"). One per segment max, not on every segment.
- Segment 1 automatically becomes the AI video hook; `type: video` forces it on
  other segments (each adds ~$0.18). The camera-motion + human-POV style block
  is appended to video prompts automatically, the quality block to every still —
  don't paste style boilerplate into `visual:` lines.

## Costs (defaults)

| What | Cost |
|---|---|
| Flux schnell still | ~$0.006 |
| Seedance Lite 5 s clip (hook or animated still) | ~$0.18 |
| Full video, `video.image_motion: ai` (default: every still animated by the image-to-video model) | ~$1.10–1.30 |
| Full video, `video.image_motion: kenburns` (free ffmpeg motion on stills) | ~$0.20–0.25 |
| `--sample` (always stills + Ken Burns, no video clips) | ~$0.04 |
| `--dry-run` | $0.00 |
| ElevenLabs voice | free tier ≈ 10k chars/month (~8 videos); attribution required if monetized |

fal has no free tier — calls fail at $0.00 balance. Animated-still clips are
cached like everything else: a re-render only re-bills segments whose image
(or the `i2v_motion_prompt`) changed.

## Styling knobs (config.yaml)

- `captions.*` — phrase-karaoke look: `phrase_font_size`, `active_color`
  (spoken-word tint), `active_scale`/`accent_scale` (pop sizes),
  `highlight.keywords` + `highlight.word_colors` (add topic words per video:
  PINK→pink, GOLDEN→gold, JUICY→amber…). Every word is pinned to a fixed
  position; only the spoken word pops (in place), colors light up as words are
  spoken. `phrase_outline` = letter-border thickness; `phrase_width_scale` and
  `phrase_space_px` calibrate spacing if words ever overlap or drift apart.
  `mode: word` = old single-word pop style.
- `video.image_motion` — `ai` (default): every still is animated with the
  Seedance image-to-video model using `video.i2v_motion_prompt` (human handheld
  movement: walking closer, arcing/rotating around the subject); `kenburns`:
  free ffmpeg zoom/pan. Samples and dry-runs always use Ken Burns.
- `transitions.*` — corporate xfade types cycled between segments;
  timing-preserving (voice/caption sync never shifts).
- `thumbnail.title_after_seconds` — big centered title over the hook after the
  card flash (0 = off).
- `sfx.volume_db`, `music.volume_db` — mix levels.
- `elevenlabs.voice_id` — Stryka (CgY1SqBRXmX1mlZzsXmR) once the account has a
  paid plan; George is the free-tier stand-in.

## Troubleshooting

- **fal 422 / schema error** → model ids drift; check `https://fal.ai/models/<model-id>`
  and fix the `fal.image_input` / `fal.video_input` payload keys in config.yaml.
- **ffmpeg not found** → set `paths.ffmpeg` in config.yaml to the full exe path.
- **Wrong-colored/mutated food in a QC frame** → edit that segment's `visual:`
  (drop the real fruit's name, restate the color), re-run with `--regen N`.
- **Duration off-target** → adjust narration length or
  `elevenlabs.voice_settings.speed` (at 1.15, ≈0.055 s per character). Changing
  narration re-bills the whole voice call; changing speed does too.
- **Neither Flux schnell nor Seedance Lite accepts `negative_prompt`** — unwanted
  artifacts are suppressed with positive phrasing (already in the style suffixes);
  never paste negative-word lists into a `visual:` line.
