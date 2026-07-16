"""Parse a canonical script markdown file into title + segments.

Format:

    # Title
    thumbnail: Short title-card text (optional; defaults to the title)
    subject: one fixed food descriptor reused in every visual (optional)

    ## Segment label (free-form)
    type: video                 (optional: video|image; segment 1 defaults to
                                 video when video.hybrid_hook is true)
    overlay: Text shown on screen (optional)
    visual: AI prompt for this segment's visual
    narration: What the voice says

`visual:` and `narration:` values may span multiple lines; a value ends at the
next `key:` line or the next `##` heading.

Consistency: write the food's exact look ONCE in `subject:` and reference it in
every visual as `{subject}` — the parser substitutes it verbatim so the food
looks identical in all clips. Avoid the literal word "blueberries"/"blueberry"
style color-traps in crowded shots (the models drift to the real fruit's color).
"""
import re
from pathlib import Path

KEYS = ("overlay", "type", "visual", "narration")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "video"


def parse_script(path: Path) -> dict:
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    title = ""
    thumbnail_text = ""
    subject = ""
    segments = []
    current = None
    current_key = None

    for line in lines:
        if line.startswith("# ") and not title and not segments:
            title = line[2:].strip()
            continue
        if current is None:
            m = re.match(r"^thumbnail:\s*(.*)$", line, re.IGNORECASE)
            if m:
                thumbnail_text = m.group(1).strip()
                continue
            m = re.match(r"^subject:\s*(.*)$", line, re.IGNORECASE)
            if m:
                subject = m.group(1).strip()
                continue
        if line.startswith("## "):
            current = {"label": line[3:].strip(), "overlay": "", "type": "", "visual": "", "narration": ""}
            segments.append(current)
            current_key = None
            continue
        if current is None:
            continue
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m and m.group(1).lower() in KEYS:
            current_key = m.group(1).lower()
            current[current_key] = m.group(2).strip()
            continue
        if current_key and line.strip():
            current[current_key] = (current[current_key] + " " + line.strip()).strip()

    if not title:
        title = Path(path).stem

    problems = []
    if not segments:
        problems.append("no '## ' segment headings found")
    for i, seg in enumerate(segments, 1):
        if not seg["narration"]:
            problems.append(f"segment {i} ({seg['label']}) has no narration")
        if not seg["visual"]:
            problems.append(f"segment {i} ({seg['label']}) has no visual prompt")
    if problems:
        raise ValueError("Script problems: " + "; ".join(problems))

    warnings = []
    for i, seg in enumerate(segments, 1):
        tells = [t for t in ("—", "…", "...", " - ") if t in seg["narration"]]
        if tells:
            warnings.append(
                f"segment {i} ({seg['label']}) narration contains AI-tell punctuation "
                f"({', '.join(repr(t) for t in tells)}) - rewrite with plain commas/periods")
    if subject:
        for i, seg in enumerate(segments, 1):
            if "{subject}" in seg["visual"]:
                seg["visual"] = seg["visual"].replace("{subject}", subject)
            else:
                warnings.append(
                    f"segment {i} ({seg['label']}) visual does not use {{subject}} - the food's look may drift between clips")
    if len(segments) != 6:
        warnings.append(f"{len(segments)} segments (house style is a 6-beat documentary)")

    return {
        "title": title,
        "slug": slugify(title),
        "thumbnail_text": thumbnail_text or title,
        "subject": subject,
        "segments": segments,
        "warnings": warnings,
    }
