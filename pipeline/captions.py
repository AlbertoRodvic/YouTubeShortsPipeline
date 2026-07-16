"""Generate an .ass subtitle file: viral karaoke captions + overlay fact cards.

Two caption modes (config `captions.mode`):

- "phrase" (default): the whole spoken phrase stays on screen and the word
  currently being said is highlighted — scaled up with a pop animation and
  tinted. Curiosity keywords and semantic colour words (PINK, GOLDEN, JUICY…)
  keep their colour the whole time and get an extra-large accent pop when
  spoken. This is the premium viral-documentary look.
- "word": legacy single-word pop (ShawnGrows style), one word at a time.

Overlay lines render as a lower-third-style fact card (semi-transparent box,
slide-in) when `captions.overlay_box` is on.
"""
import re


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def _esc(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def _bgr(hex_rgb: str) -> str:
    """ASS primary colours are &HBBGGRR&; convert an 'RRGGBB' (or '#RRGGBB') string."""
    h = hex_rgb.strip().lstrip("#")
    if len(h) != 6:
        return "&HFFFFFF&"
    rr, gg, bb = h[0:2], h[2:4], h[4:6]
    return f"&H{bb}{gg}{rr}&".upper()


def _word_key(word: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", word.upper())


def _highlight_color(word: str, hl: dict) -> str:
    """Return an ASS colour value for a caption word, or '' to leave it default white.

    Matches ignore case and punctuation, so SHOULDN'T -> SHOULDNT and WORLD'S -> WORLDS.
    Explicit per-word colours win over the shared curiosity-keyword colour.
    """
    key = _word_key(word)
    if not key:
        return ""
    for k, v in (hl.get("word_colors") or {}).items():
        if _word_key(k) == key:
            return _bgr(v)
    if key in {_word_key(k) for k in (hl.get("keywords") or [])}:
        return _bgr(hl.get("keyword_color", "FF9F0A"))
    return ""


def _phrases(words, max_words: int, gap: float = 0.6):
    """Group timed words into caption phrases: break at sentence punctuation,
    long pauses, or the word cap. A stranded final word joins the previous phrase."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        brk = len(cur) >= max_words or w["text"][-1:] in ".!?,;:…"
        if not brk and i + 1 < len(words):
            brk = words[i + 1]["start"] - w["end"] > gap
        if brk or i + 1 == len(words):
            groups.append(cur)
            cur = []
    if len(groups) >= 2 and len(groups[-1]) == 1 and len(groups[-2]) < max_words + 1:
        groups[-2].extend(groups.pop())
    return groups


def _split_lines(texts):
    """Insert a fixed line break so the phrase lays out as up to two stable,
    centred lines (a moving wrap point between karaoke frames looks jittery)."""
    if len(texts) < 3 and sum(len(t) for t in texts) <= 16:
        return [texts]
    total = sum(len(t) + 1 for t in texts)
    acc, best, best_diff = 0, 1, 10 ** 9
    for i, t in enumerate(texts[:-1]):
        acc += len(t) + 1
        diff = abs(total - 2 * acc)
        if diff < best_diff:
            best, best_diff = i + 1, diff
    return [texts[:best], texts[best:]]


def _load_font(name: str, size: int):
    """Best-effort font metrics for word layout (PIL is already a dependency)."""
    from PIL import ImageFont

    candidates = []
    if "black" in name.lower():
        candidates.append("ariblk.ttf")
    candidates += [name.replace(" ", "") + ".ttf", "arialbd.ttf", "arial.ttf"]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return None


def _wlen(font, text: str, size: int) -> float:
    if font is not None:
        return float(font.getlength(text))
    return len(text) * size * 0.62  # rough Arial-Black fallback


def _phrase_events(words, cap, hl, hl_on, offset, W, H, min_start=0.0):
    """One Dialogue PER WORD, each pinned to a fixed pixel position for the whole
    phrase. The active word pops (scale + colour) IN PLACE via \\t transforms while
    every other word keeps a constant size and position — no line reflow, no
    jitter. Colours light up when a word is spoken (never before) and stay on.
    """
    max_words = max(2, int(cap.get("phrase_max_words", 4)))
    active_scale = int(cap.get("active_scale", 120))
    accent_scale = int(cap.get("accent_scale", 140))
    active_color = _bgr(cap.get("active_color", "FFD400"))
    upper = cap.get("uppercase", True)
    fs = int(cap.get("phrase_font_size", 76))
    font = _load_font(cap.get("font", "Arial Black"), fs)
    yc = int(cap.get("y_center", 1440))
    lh = int(fs * 1.3)
    max_line_w = W - 90
    events = []
    groups = _phrases(words, max_words)
    for gi, g in enumerate(groups):
        texts = [w["text"].upper() if upper else w["text"] for w in g]
        colors = [_highlight_color(t, hl) if hl_on else "" for t in texts]
        lines = _split_lines(texts)
        disp_start = max(g[0]["start"] + offset, min_start)
        hold_end = g[-1]["end"] + 0.7
        if gi + 1 < len(groups):
            hold_end = min(hold_end, groups[gi + 1][0]["start"])
        disp_end = max(hold_end, g[-1]["end"]) + offset
        if disp_end - disp_start < 0.05:
            continue
        j = 0
        for li, line in enumerate(lines):
            # width_scale calibrates PIL's measurement to libass's actual rendering
            wscale = float(cap.get("phrase_width_scale", 0.86))
            widths = [_wlen(font, t, fs) * wscale for t in line]
            space = float(cap.get("phrase_space_px", 26))
            total = sum(widths) + space * (len(line) - 1)
            k = min(1.0, max_line_w / total) if total else 1.0
            fs_line = int(fs * k)
            if k < 1.0:
                widths = [w * k for w in widths]
                space *= k
            x = (W - (sum(widths) + space * (len(line) - 1))) / 2
            y = int(yc + (li - (len(lines) - 1) / 2) * lh)
            for m, t in enumerate(line):
                wm = g[j]
                color = colors[j]
                cx = int(x + widths[m] / 2)
                x += widths[m] + space
                s = accent_scale if color else active_scale
                fill = color or active_color
                a1 = max(0, int((wm["start"] + offset - disp_start) * 1000))
                tags = [f"\\an5\\pos({cx},{y})"]
                if fs_line != fs:
                    tags.append(f"\\fs{fs_line}")
                tags.append(r"\fad(60,0)")
                # pop up + light up exactly when the word is spoken...
                tags.append(f"\\t({a1},{a1 + 90},\\fscx{s}\\fscy{s}\\1c{fill})")
                if j + 1 < len(g):  # ...then settle back down, keeping the colour
                    b1 = max(a1 + 90, int((g[j + 1]["start"] + offset - disp_start) * 1000))
                    back = color if color else "&HFFFFFF&"
                    tags.append(f"\\t({b1},{b1 + 80},\\fscx100\\fscy100\\1c{back})")
                events.append(
                    f"Dialogue: 0,{_ts(disp_start)},{_ts(disp_end)},Phrase,,0,0,0,,"
                    f"{{{''.join(tags)}}}{_esc(t)}"
                )
                j += 1
    return events


def _word_events(words, cap, hl, hl_on, offset):
    """Legacy mode: big single-word (or n-word) pop captions."""
    events = []
    group = max(1, int(cap.get("words_per_caption", 1)))
    chunks = [words[i:i + group] for i in range(0, len(words), group)]
    pop = r"{\fad(40,0)\fscx70\fscy70\t(0,70,\fscx100\fscy100)}"
    upper = cap.get("uppercase", True)
    for i, ch in enumerate(chunks):
        start = ch[0]["start"]
        end = ch[-1]["end"]
        if i + 1 < len(chunks):
            # hold the word through short pauses, but never past the next word
            end = max(min(chunks[i + 1][0]["start"], end + 0.5), start + 0.12)
        parts = []
        for w in ch:
            t = w["text"].upper() if upper else w["text"]
            color = _highlight_color(t, hl) if hl_on else ""
            # reset to white after a tinted word so multi-word chunks don't bleed colour
            parts.append(f"{{\\c{color}}}{_esc(t)}{{\\c&HFFFFFF&}}" if color else _esc(t))
        text = " ".join(parts)
        events.append(f"Dialogue: 0,{_ts(start + offset)},{_ts(end + offset)},Word,,0,0,0,,{pop}{text}")
    return events


def build_ass(words, segments_meta, seg_times, cfg, offset: float = 0.0, title_text: str = "",
              min_start: float = 0.0) -> str:
    """offset shifts every event later, e.g. when a thumbnail card is prepended.

    title_text, if given, is shown as a big centred title for the first few
    seconds after the thumbnail card (config thumbnail.title_after_seconds).
    min_start clamps every on-screen text so NOTHING overlaps the thumbnail
    card or its transition — the first frames show only the card."""
    cap = cfg["captions"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    font = cap.get("font", "Arial Black")
    word_margin_v = H - int(cap.get("y_center", 1440))
    if cap.get("overlay_box", True):
        # BorderStyle 3: OutlineColour fills a box behind the text -> lower-third card
        overlay_style = (
            f"Style: Overlay,{font},{cap.get('overlay_font_size', 62)},&H0000E6FF,&H00FFFFFF,"
            f"&H78000000,&H00000000,-1,0,0,0,100,100,0,0,3,14,0,8,80,80,{cap.get('overlay_y', 380)},1"
        )
    else:
        overlay_style = (
            f"Style: Overlay,{font},{cap.get('overlay_font_size', 62)},&H0000E6FF,&H00FFFFFF,"
            f"&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,2,8,80,80,{cap.get('overlay_y', 380)},1"
        )
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,{font},{cap.get('font_size', 105)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,9,2,2,60,60,{word_margin_v},1
Style: Phrase,{font},{cap.get('phrase_font_size', 76)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,{cap.get('phrase_outline', 7)},2,5,0,0,0,1
Style: Title,{font},{(cfg.get('thumbnail') or {}).get('font_size', 130)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,10,3,5,60,60,0,1
{overlay_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    hl = cap.get("highlight") or {}
    hl_on = bool(hl.get("enabled", False))
    # never render punctuation-only tokens (a stray "—" or "..." as its own
    # caption word is a dead giveaway of scripted text)
    words = [w for w in words if re.search(r"[A-Za-z0-9À-ɏ]", w["text"])]
    if cap.get("mode", "phrase") == "phrase":
        events = _phrase_events(words, cap, hl, hl_on, offset, W, H, min_start)
    else:
        events = _word_events(words, cap, hl, hl_on, offset)

    thumb = cfg.get("thumbnail") or {}
    title_secs = float(thumb.get("title_after_seconds", 3.0))
    if title_text and title_secs > 0:
        txt = title_text.upper() if thumb.get("uppercase", True) else title_text
        tw = txt.split()
        tlines = _split_lines(tw) if len(tw) > 1 else [tw]
        body = "\\N".join(" ".join(_esc(t) for t in line) for line in tlines)
        ty = int(float(thumb.get("y_center_frac", 0.42)) * H)
        t0 = max(offset, min_start)
        events.append(
            f"Dialogue: 2,{_ts(t0)},{_ts(t0 + title_secs)},Title,,0,0,0,,"
            f"{{\\pos({W // 2},{ty})\\fad(150,350)\\fscx88\\fscy88\\t(0,220,\\fscx100\\fscy100)}}{body}"
        )

    cx = W // 2
    oy = int(cap.get("overlay_y", 380))
    for seg, t in zip(segments_meta, seg_times):
        if seg.get("overlay"):
            txt = seg["overlay"].upper() if cap.get("uppercase", True) else seg["overlay"]
            events.append(
                f"Dialogue: 1,{_ts(max(t['start'] + offset, min_start))},{_ts(t['end'] + offset)},Overlay,,0,0,0,,"
                f"{{\\fad(200,200)\\move({cx},{oy + 26},{cx},{oy},0,300)}}{_esc(txt)}"
            )

    if min_start > 0:
        events = _clamp_events(events, min_start)
    return header + "\n".join(events) + "\n"


def _clamp_events(events, min_start: float):
    """Push any event that would start before min_start to min_start (drop it if
    it would also end by then) so no text renders over the thumbnail card."""
    out = []
    floor = _ts(min_start)
    for ev in events:
        pre, start, end, post = ev.split(",", 3)
        if start < floor:  # ASS h:mm:ss.cc strings compare chronologically (<1h)
            if end <= floor:
                continue
            ev = f"{pre},{floor},{end},{post}"
        out.append(ev)
    return out
