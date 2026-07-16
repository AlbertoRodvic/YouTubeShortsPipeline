---
name: make-video
description: Turn a video script into a finished 9:16 YouTube Short with ElevenLabs voice, AI-generated visuals, and karaoke captions. Use whenever the user provides a script or asks to make, render, or produce a video.
---

# /make-video — script to finished Short

The pipeline lives in `pipeline/` (run from the repo root). API keys live in `.env`
(`ELEVENLABS_API_KEY`, `FAL_KEY`); voice, models, and caption styling in `config.yaml`.
Never print key values.

## Workflow

0. **Topic-only input.** If the user gives just a food/topic ("FOOD: pink blueberries")
   instead of a script, write the full 6-beat narration yourself: analyze the subject's
   appearance, colors, texture, origin, growing environment, preparation, cultural
   importance, and viral hook angle (WebSearch if unsure of facts — never invent food
   facts). Show the drafted script to the user before any paid render; a free
   `--dry-run` while they read costs nothing.

1. **Normalize the script.** Whatever the user pastes (timestamped shooting script,
   loose notes, or just narration), rewrite it as canonical markdown at `scripts/<slug>.md`:

   ```
   # <Title>
   thumbnail: <short punchy title-card text, optional; defaults to the title>
   subject: <ONE fixed food descriptor: exact color, shape, size, texture>

   ## <Segment label>
   type: video            <- only to force an AI video clip; omit otherwise
                             (segment 1 becomes video automatically in hybrid mode)
   overlay: <text shown on screen, optional>
   visual: <one image/video prompt, referencing {subject}>
   narration: <exactly what the voice reads>
   ```

   - Keep the user's narration verbatim (fix only typos and encoding artifacts).
     The narration is the product; don't rewrite it without asking.
   - **No AI-tell punctuation** (user rule 2026-07-15): narration must read like
     spoken speech — no em dashes, no ellipses, no "So..." dramatic dots; use plain
     commas and periods. The parser warns on these and the caption layer drops
     punctuation-only tokens, but write it clean in the first place.
   - If visual prompts are missing, write them: concrete subject + setting + lighting
     + mood, photorealistic, vertical-friendly composition with the subject centered.
     One clear subject per prompt. Avoid text-in-image, hands performing precise
     actions, and multi-person scenes — image models fail at these.
   - **Consistency rule:** write the food's exact look ONCE in `subject:` and put
     `{subject}` in every segment's `visual:` — the parser substitutes it verbatim
     (and warns when a visual skips it). Re-describing the subject differently per
     prompt produces a different-looking food per clip, which reads as fake.
     Color-trap warning: in crowded shots the real fruit's name ("blueberries")
     drags the model to the real color — describe shape + wanted color instead.
   - **Fact cards:** use `overlay:` for premium motion-graphic labels — short
     card-style facts like "ORIGIN: NORTH AMERICA" or "NATURAL PINK PIGMENTATION"
     (it renders as an animated lower-third card). One per segment max, not on
     every segment.
   - The standing visual style is applied BY THE PIPELINE, not by hand: the
     camera-motion + human-POV block is auto-appended to every `type: video` prompt
     (config `video.video_style_suffix`), the quality block to every still
     (`image_style_suffix`). Do NOT paste style boilerplate into `visual:` lines.
     The negative block is documented in config but is NOT sendable — neither Flux
     schnell nor Seedance Lite accepts `negative_prompt` — so suppress failure modes
     with positive phrasing, never by listing negative words in a prompt.
   - Structure as the channel's 6-beat documentary (see "Channel format" below): Hook,
     Introduction, Unique Feature, Origin, Experience, Final Wow. Aim for 6 segments,
     ~10–12 s each, total 61–70 s; the final narration ends on a question that invites
     comments. Shorter 4-beat scripts still render fine — match the source.

2. **Preflight.** Check `.env` has both keys and `config.yaml` has `elevenlabs.voice_id`.
   If missing, stop and ask the user. For a brand-new script, a `--dry-run` first
   (free) confirms parsing, timing, and caption layout before spending API credits.

3. **Render:** `python -m pipeline.make_video scripts/<slug>.md`
   Flags: `--dry-run` (free placeholders), `--no-hook-video` (all images, cheapest),
   `--regen N` (regenerate only segment N's visual), `--force` (ignore caches).
   Everything is cached in `output/<slug>/work/` keyed by prompt hash — re-runs only
   regenerate what changed, so iterating is nearly free.

   **Samples:** if the user's request contains the word "sample" (or asks for a
   preview), that ALWAYS means sample-only: render with `--sample` — real Flux
   images for every beat (~$0.04) but NO Seedance hook clip — and never the full
   render, no matter what else the request says. Nothing is wasted on upgrade: images
   and TTS are cached, so the follow-up full render only bills the hook clip (~$0.18).
   Only run the full render after they explicitly approve the sample.

4. **QC the result.** One frame per segment midpoint is auto-exported to
   `output/<slug>/qc/seg_NN.png` — Read each image. (Segment times for extra frames
   are in `output/<slug>/summary.json`.)

   Check: visual matches the narration beat, no mangled anatomy or garbled text in the
   generated images, captions legible and not colliding with the overlay text, and the
   colored highlights (config `captions.highlight`) land on the right words. Confirm the
   duration fits the 61–70 s documentary target (Shorts now allows up to 3 min; TikTok/
   Reels longer) — tune `elevenlabs.voice_settings.speed` if it runs over.

   Full quality checklist (the production-system spec): 61–70 s ✓ 6 clips ✓ 9:16 ✓
   the food looks IDENTICAL across all segments ✓ images realistic (no CGI/plastic
   look) ✓ phrase captions readable with the active word popping ✓ transitions smooth
   (grab a frame ~0.15 s after a segment boundary to see one mid-blend) ✓ music +
   sfx present but under the voice ✓ overall feel = premium documentary, not an AI
   slideshow.

   Also Read `output/<slug>/thumbnail.png` — the title card baked into the video's
   first 0.2 s (Shorts don't accept custom thumbnail uploads, so the card lives in the
   video where YouTube's frame picker can grab it; `thumbnail.mode/seconds` in config).
   Check the text is readable against the image and not awkwardly wrapped.

5. **Fix what's bad.** Edit that segment's `visual:` prompt in the script md and re-run
   with `--regen N`. Only that visual is re-billed.

6. **Deliver.** Report: the mp4 path, duration, estimated cost from `summary.json`, and
   the upload info from the auto-generated `output/<slug>/metadata.txt` (improve the
   title/description creatively where it helps). Do not upload anywhere — the user
   reviews and uploads manually.

## Channel format (viral food / nature documentary)

The channel's house style — see memory `documentary-production-system`. Apply when
writing or normalizing scripts:

- **6 clips**, one per `##` segment, ~10–12 s each, total 61–70 s. The beats:
  1. **Hook** — the single most unbelievable shot; first line creates instant curiosity.
  2. **Introduction** — what it is, full appearance, where it's from.
  3. **Unique feature** — the one detail that makes it special (macro / close-up).
  4. **Origin / discovery** — where it comes from, how people found it.
  5. **Experience** — imagine trying it: scale, interaction, the taste/effect moment.
  6. **Final wow** — the hero shot; narration ends on a question inviting comments
     ("Would you try this?", "Have you ever seen anything like it?").
- **Visuals**: cinematic documentary, ultra-real texture, professional food/nature
  photography, one subject per shot. The global quality + camera-motion + stability
  style is already wired through `image_style_suffix` and the video-hook prompts.
- **Captions**: phrase-karaoke (`captions.mode: phrase`) — every word of the phrase is
  pinned to a fixed pixel position (measured per word); the currently spoken word pops
  IN PLACE (scale + `active_color` tint) while all other words stay perfectly still —
  no line reflow, ever. Colors light up only from the moment a word is spoken (never
  before): curiosity words (RARE, SECRET, ZERO…) get the accent color and the bigger
  `accent_scale` pop; food/texture words light up in matching colors (PINK→pink,
  GOLDEN→gold, JUICY→amber) and keep them for the rest of the phrase. Thick outline
  (`phrase_outline`) keeps text crisp on bright scenes; `phrase_width_scale` /
  `phrase_space_px` calibrate word spacing. Add topic-specific words to the config
  lists when a video leans on a particular color or feeling word. `mode: word` brings
  back the old single-word pop.
- **Video motion**: every `type: video` prompt gets a human-POV clause ("first person
  point of view of a person walking up to the [subject] and slowly moving around it,
  natural handheld camera sway like human footsteps") plus the standing camera-motion
  block — the movement should feel like a person filming handheld, not a synthetic
  dolly.
- **Title overlay**: the video title pops up big and centered for
  `thumbnail.title_after_seconds` (default 3 s) right after the thumbnail card flash.
- **Pacing/editing**: a visual change every ~5–8 s (the 6 beats handle this); corporate
  xfade transitions between segments (config `transitions`, timing-preserving — segment
  start times don't shift); music bed ducked under the voice.
- **Sound design**: files in `assets/sfx/` are mixed automatically — `whoosh*` swells
  into each segment change, `impact*`/`hit*` lands on the hook at 0:00. Empty folder =
  skipped; suggest the user drop in royalty-free sfx (or generate once via ElevenLabs
  sound-effects API — paid, ask first).

## Cost notes

- **Visual tier is the main cost lever.** Current default (user-approved 2026-07-15):
  `video.image_motion: ai` — the hook is a text-to-video clip and every other still is
  animated with the Seedance image-to-video model + human handheld/rotating motion
  prompt (~$1.10–1.30 per full video). `image_motion: kenburns` in config is the cheap
  fallback (~$0.20/video). `--sample` and `--dry-run` always use Ken Burns, so previews
  stay ~$0.04 / free.
- Flux schnell images ~$0.006 each; each Seedance 5 s clip (hook or animated still)
  ~$0.18. Animated clips are cached — re-renders only re-bill segments whose image or
  motion prompt changed.
- fal model ids live in `config.yaml` (`fal.image_model`, `fal.video_model`). If a fal
  call fails with a 422/schema error, check the model page at
  `https://fal.ai/models/<model-id>` and fix the input payload keys in config.
- Music: any royalty-free mp3/wav placed in `assets/music/` gets auto-mixed and ducked
  under the voice; the folder being empty just skips music.
