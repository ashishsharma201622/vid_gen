

"""
Free "motion video" pipeline, light enough for a 4GB laptop with no GPU.

prompt -> Gemini (hook + short scenes) -> Pollinations (one image per scene)
       -> edge-tts (voice) -> ffmpeg: camera motion, big animated captions,
          crossfade/slide transitions, optional background music -> final.mp4
"""
import asyncio
import json
import logging
import os
import random
import re
import shutil
import struct
import subprocess
import time
import urllib.parse
from pathlib import Path

import edge_tts
import requests

log = logging.getLogger("pipeline")


def _env(name: str, default: str = "") -> str:
    """Read a setting and remove stray spaces, quotes and line breaks (common after copy-paste)."""
    return os.getenv(name, default).strip().strip("\"'").strip()


GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.5-flash-lite")
VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
TTS_RATE = os.getenv("TTS_RATE", "+8%")  # a little faster = punchier
POLLINATIONS_KEY = _env("POLLINATIONS_API_KEY")   # from enter.pollinations.ai
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "")   # empty = their default image model

WIDTH, HEIGHT, FPS = 720, 1280, 25  # vertical: Shorts / TikTok / Reels
LEAD, TAIL, XFADE = 0.30, 0.35, 0.30  # seconds: silence before/after speech, transition length
HERE = Path(__file__).parent
MUSIC_DIR = HERE / "music"  # drop any royalty-free mp3 in here (optional)

SCRIPT_INSTRUCTIONS = """You write short vertical videos (35-55 seconds) for YouTube Shorts and TikTok.
Return ONLY JSON with this shape:
{"title": "catchy title under 90 chars",
 "description": "2-3 sentences plus 3 hashtags",
 "scenes": [{"narration": "one short punchy sentence",
             "image_prompt": "detailed visual description"}]}
Rules:
- 9 to 12 scenes. Scene 1 is a hook that grabs attention immediately.
- Each narration is ONE short sentence, at most 14 words. Simple spoken language.
- Each image_prompt: vivid, cinematic, dramatic lighting, vertical composition, no text or letters
  in the image. Repeat the full description of recurring characters and the art style in EVERY
  image_prompt so they look the same in every scene.
- Never use double quote characters inside any text value; use single quotes instead."""

SCRIPT_SCHEMA = {  # forces Gemini to return exactly this shape, with valid JSON
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "scenes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"narration": {"type": "STRING"}, "image_prompt": {"type": "STRING"}},
                "required": ["narration", "image_prompt"],
            },
        },
    },
    "required": ["title", "description", "scenes"],
}


# ---------------------------------------------------------------- script (Gemini)
def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):  # in case the model wraps the JSON in a code fence
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text)


def make_script(user_prompt: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing or empty in .env")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": GEMINI_API_KEY}  # header, so the key never shows up in URLs or logs
    use_schema = True
    last_error = None
    for attempt in range(1, 5):  # small models sometimes return broken JSON: just ask again
        config = {"responseMimeType": "application/json"}
        if use_schema:
            config["responseSchema"] = SCRIPT_SCHEMA
        body = {
            "systemInstruction": {"parts": [{"text": SCRIPT_INSTRUCTIONS}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": config,
        }
        r = requests.post(url, json=body, headers=headers, timeout=90)
        if r.status_code == 400 and use_schema:
            log.warning("Gemini rejected the schema (%s). Retrying without it.", r.text[:200])
            use_schema = False
            continue
        if r.status_code in (401, 403):
            raise RuntimeError(f"Gemini refused the key or request (HTTP {r.status_code}). Check GEMINI_API_KEY "
                               f"in .env (no quotes, no spaces) or create a new key in Google AI Studio. "
                               f"Details: {r.text[:200]}")
        if not r.ok:
            raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")

        text = ""
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            script = _parse_json(text)
            if script.get("scenes"):
                return script
            raise ValueError("no scenes in the answer")
        except (KeyError, IndexError, ValueError) as e:
            last_error = e
            log.warning("Gemini attempt %d gave unusable JSON (%s). Start of answer: %r",
                        attempt, e, text[:200])
    raise RuntimeError(f"Gemini kept returning bad JSON: {last_error}")


# ---------------------------------------------------------------- images (Pollinations)
def fetch_image(image_prompt: str, out: Path, seed: int) -> None:
    if not POLLINATIONS_KEY:
        raise RuntimeError("POLLINATIONS_API_KEY is missing in .env (create a key at enter.pollinations.ai)")
    url = "https://gen.pollinations.ai/image/" + urllib.parse.quote(image_prompt, safe="")
    params = {"width": WIDTH, "height": HEIGHT, "seed": seed}
    if POLLINATIONS_MODEL:
        params["model"] = POLLINATIONS_MODEL
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}
    refusals = {
        401: "the key is missing or wrong",
        402: "you are out of Pollinations credits (Pollen)",
        403: "this key is not allowed to use that image model",
        404: "the endpoint or model was not found",
    }

    last = ""
    r = None
    for attempt in range(1, 4):  # busy service: retry on hiccups
        try:
            r = requests.get(url, params=params, headers=headers, timeout=120)
        except requests.RequestException as e:
            last = f"network error: {e}"
            r = None
        else:
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                out.write_bytes(r.content)
                return
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in refusals:  # retrying will not help, so fail fast with the reason
                raise RuntimeError(f"Pollinations refused: {refusals[r.status_code]}. ({last})")
        log.warning("Image attempt %d failed: %s", attempt, last)
        wait = 3 * attempt
        if r is not None and str(r.headers.get("Retry-After", "")).isdigit():
            wait = int(r.headers["Retry-After"])
        time.sleep(min(wait, 30))
    raise RuntimeError(f"Image generation failed after 3 tries. Last problem: {last}")


# ---------------------------------------------------------------- voice (edge-tts)
async def _tts(text: str, out: Path) -> None:
    await edge_tts.Communicate(text, VOICE, rate=TTS_RATE).save(str(out))


# ---------------------------------------------------------------- ffmpeg helpers
def _ffmpeg(args: list, cwd: Path) -> None:
    res = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                         cwd=str(cwd), capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + res.stderr.strip()[-600:])


def media_seconds(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(res.stdout.strip())


# ---------------------------------------------------------------- camera motion
MOTIONS = ["in", "panright", "out", "panleft", "tiltup"]  # cycled scene by scene


def motion_filter(kind: str, frames: int) -> str:
    """zoompan: the 'camera' slowly moves over the still image. No commas in the
    expressions on purpose (commas would break the ffmpeg filter string)."""
    n = max(frames - 1, 1)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if kind == "in":
        z, x, y = f"1+0.22*on/{n}", cx, cy
    elif kind == "out":
        z, x, y = f"1.22-0.22*on/{n}", cx, cy
    elif kind == "panright":
        z, x, y = "1.20", f"(iw-iw/zoom)*on/{n}", cy
    elif kind == "panleft":
        z, x, y = "1.20", f"(iw-iw/zoom)*(1-on/{n})", cy
    else:  # tiltup
        z, x, y = "1.20", cx, f"(ih-ih/zoom)*(1-on/{n})"
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"


# ---------------------------------------------------------------- captions
FONT_CANDIDATES = [  # tried in this order if you did not choose a font yourself
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font_info(path: Path) -> tuple:
    """(family name, bold flag) read from the font file itself, so the caption style
    always matches the font (a wrong name means libass draws NOTHING, silently)."""
    try:
        d = path.read_bytes()
        num = struct.unpack(">H", d[4:6])[0]
        for i in range(num):
            tag, _, off, _ = struct.unpack(">4sIII", d[12 + 16 * i:28 + 16 * i])
            if tag == b"name":
                count, str_off = struct.unpack(">HH", d[off + 2:off + 6])
                names = {}
                for j in range(count):
                    pid, _, _, nid, ln, o = struct.unpack(">HHHHHH", d[off + 6 + 12 * j:off + 18 + 12 * j])
                    raw = d[off + str_off + o: off + str_off + o + ln]
                    text = raw.decode("utf-16-be" if pid in (0, 3) else "latin-1", errors="ignore")
                    if nid in (1, 2) and (nid not in names or pid == 3):
                        names[nid] = text
                return names.get(1) or path.stem, 1 if "bold" in names.get(2, "").lower() else 0
    except Exception:
        pass
    return path.stem, 0


def _find_font():
    custom = os.getenv("CAPTION_FONT_FILE", "")
    if custom and Path(custom).exists():
        return Path(custom)
    mine = HERE / "fonts"  # drop a .ttf/.otf here (e.g. Anton-Regular.ttf) to choose your own
    if mine.is_dir():
        found = sorted(list(mine.glob("*.ttf")) + list(mine.glob("*.otf")))
        if found:
            return found[0]
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return Path(p)
    android = Path("/system/fonts")  # phones (Termux)
    if android.is_dir():
        files = sorted(android.glob("*.ttf"))
        bold = [f for f in files if "bold" in f.name.lower() and "italic" not in f.name.lower()]
        roboto = [f for f in files if f.name.lower().startswith("roboto")]
        pick = bold or roboto or files
        if pick:
            return pick[0]
    return None


def prepare_font(job_dir: Path):
    """Copy one font next to the job so libass can always find it. None = no font found."""
    path = _find_font()
    if path is None:
        log.warning("No caption font found, so this video gets no captions. "
                    "Put a .ttf file (for example Anton-Regular.ttf) in a 'fonts' folder next to bot.py.")
        return None
    fonts = job_dir / "fonts"
    fonts.mkdir(exist_ok=True)
    shutil.copy(path, fonts / path.name)
    family, bold = _font_info(path)
    log.info("Caption font: %s (%s)", family, path.name)
    return family, bold


def _ass_time(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def build_ass(narration: str, speech_start: float, speech_len: float, family: str, bold: int, out: Path) -> None:
    """Big 'shorts style' captions: 2-3 words on screen, the spoken word highlighted.
    Word timing is estimated from word length (good enough for a single short sentence)."""
    words = [w for w in re.sub(r"[{}\\]", "", narration).split() if w]
    if not words:
        out.write_text("")
        return
    weights = [len(w) + 2 + (4 if w[-1] in ".,!?;:" else 0) for w in words]
    total, t, timings = sum(weights), speech_start, []
    for wt in weights:
        d = speech_len * wt / total
        timings.append((t, t + d))
        t += d

    chunks, cur, chars = [], [], 0  # group into short lines
    for i, w in enumerate(words):
        if cur and (len(cur) == 3 or chars + len(w) > 13):
            chunks.append(cur)
            cur, chars = [], 0
        cur.append(i)
        chars += len(w) + 1
    if cur:
        chunks.append(cur)

    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{family},70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,{bold},0,0,0,100,100,1,0,1,7,2,2,50,50,340,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for chunk in chunks:
        for active in chunk:
            parts = []
            for j in chunk:
                w = words[j].upper()
                parts.append(r"{\c&H00E5FF&}" + w + r"{\c&HFFFFFF&}" if j == active else w)
            a, b = timings[active]
            lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Cap,,0,0,0,,{' '.join(parts)}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- one scene
def render_scene(image: Path, audio: Path, out: Path, idx: int, narration: str, font: tuple) -> float:
    """image + voice -> a moving clip with captions. Returns the clip length in seconds."""
    job_dir = image.parent
    speech = media_seconds(audio)
    dur = LEAD + speech + TAIL
    frames = int(round(dur * FPS))
    ass = job_dir / f"s{idx}.ass"
    if font:
        build_ass(narration, LEAD, speech, font[0], font[1], ass)

    look = (f"scale=1080:1920,{motion_filter(MOTIONS[idx % len(MOTIONS)], frames)},"
            "eq=contrast=1.06:saturation=1.15,format=yuv420p")
    fontsdir = ":fontsdir=fonts" if (job_dir / "fonts").is_dir() else ""
    lead_ms = int(LEAD * 1000)

    def run(vf: str) -> None:  # relative file names + cwd=job_dir avoids Windows path escaping trouble
        _ffmpeg(["-loop", "1", "-i", image.name, "-i", audio.name, "-vf", vf,
                 "-af", f"adelay={lead_ms}:all=1,apad", "-t", f"{dur:.3f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-r", str(FPS),
                 "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out.name], job_dir)

    if font:
        try:
            run(f"{look},subtitles={ass.name}{fontsdir}")
        except RuntimeError as e:
            log.warning("Captions failed (%s). Rendering this scene without captions.", str(e)[:200])
            run(look)
    else:
        run(look)
    ass.unlink(missing_ok=True)
    return media_seconds(out)


# ---------------------------------------------------------------- join everything
TRANSITIONS = ["fade", "slideleft", "fade", "slideright"]


def pick_music():
    if not MUSIC_DIR.is_dir():
        return None
    files = [p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac")]
    return random.choice(files) if files else None


def assemble(clips: list, out: Path, music=None) -> None:
    """Crossfade/slide between scenes, mix in optional music, fade the sound out at the end."""
    job_dir = out.parent
    durs = [media_seconds(c) for c in clips]
    n = len(clips)
    inputs = []
    for c in clips:
        inputs += ["-i", c.name]

    parts, cur_v, cur_a = [], "[0:v]", "[0:a]"
    for k in range(1, n):
        offset = sum(durs[:k]) - k * XFADE
        parts.append(f"{cur_v}[{k}:v]xfade=transition={TRANSITIONS[(k - 1) % len(TRANSITIONS)]}"
                     f":duration={XFADE}:offset={offset:.3f}[v{k}]")
        parts.append(f"{cur_a}[{k}:a]acrossfade=d={XFADE}:c1=tri:c2=tri[a{k}]")
        cur_v, cur_a = f"[v{k}]", f"[a{k}]"
    total = sum(durs) - (n - 1) * XFADE

    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        parts.append(f"[{n}:a]volume=0.10,afade=t=in:d=1.0[m]")
        parts.append(f"{cur_a}[m]amix=inputs=2:duration=first:normalize=0[mix]")
        cur_a = "[mix]"
    parts.append(f"{cur_a}afade=t=out:st={max(total - 1.2, 0):.2f}:d=1.2[aout]")

    _ffmpeg([*inputs, "-filter_complex", ";".join(parts), "-map", (cur_v if n > 1 else "0:v"), "-map", "[aout]",
             "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", out.name], job_dir)


# ---------------------------------------------------------------- the whole thing
def build_video(user_prompt: str, job_dir: Path, progress=None) -> dict:
    """Runs the whole pipeline. Blocking: call it from a thread.
    progress(text) is called at each step so the bot can show it in Telegram."""
    def say(text: str) -> None:
        log.info(text)
        if progress:
            try:
                progress(text)
            except Exception:
                pass

    job_dir.mkdir(parents=True, exist_ok=True)
    say("✍️ Writing the script...")
    script = make_script(user_prompt)
    (job_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    font = prepare_font(job_dir)

    scenes = script["scenes"]
    clips = []
    for i, scene in enumerate(scenes):
        n = f"{i + 1}/{len(scenes)}"
        img, mp3, clip = job_dir / f"s{i}.jpg", job_dir / f"s{i}.mp3", job_dir / f"s{i}.mp4"
        say(f"🎨 Scene {n}: making the image...")
        fetch_image(scene["image_prompt"], img, seed=i + 1)
        say(f"🎙 Scene {n}: recording the voice...")
        asyncio.run(_tts(scene["narration"], mp3))
        say(f"🎬 Scene {n}: adding motion and captions...")
        render_scene(img, mp3, clip, i, scene["narration"], font)
        clips.append(clip)
        img.unlink(missing_ok=True)  # save disk on the old laptop
        mp3.unlink(missing_ok=True)

    say("🔗 Joining scenes with transitions" + (" and music..." if pick_music() else "..."))
    final = job_dir / "final.mp4"
    assemble(clips, final, pick_music())
    for c in clips:
        c.unlink(missing_ok=True)
    shutil.rmtree(job_dir / "fonts", ignore_errors=True)
    return {"video": str(final), "title": script["title"], "description": script["description"]}




