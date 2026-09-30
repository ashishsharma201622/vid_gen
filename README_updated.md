# Vid_Gen — Free AI Video Generator

AI video automation project running from Android Termux, with Gemini as the Director/Scriptwriter, edge-tts for voice generation, and a Kaggle GPU notebook as the heavy image/video-rendering worker.

Goal:

Telegram `/video <prompt>` → Gemini story → consistent AI character images + AI voices → (next: GPU-rendered video clips) → subtitles + FFmpeg → final vertical MP4 → Telegram.

## 1. Project Location

Main Termux workspace:

```
/data/data/com.termux/files/home/AJ_projects/Vid_Gen
```

Equivalent Termux shortcut:

```
cd ~/AJ_projects/Vid_Gen
```

GitHub:

```
https://github.com/ashishsharma201622/vid_gen
```

## 2. Target Architecture

```
Telegram
   │
   │ /video <prompt>
   ▼
Android / Termux
   │
   ├── bot.py
   ├── director.py
   ├── tts.py
   ├── cloud_worker.py
   └── pipeline.py
   │
   ├───────────────┐
   ▼               ▼
Gemini          edge-tts
Director        voice MP3s
   │
   ▼
story JSON
   │
   ▼
Kaggle GPU Worker (FastAPI + ngrok tunnel)
   │
   ├── anchor image (main character)
   ├── per-scene images (IP-Adapter, consistent character)
   └── (next) image → video clips
   │
   ▼
scene images / MP4s
   │
   ▼
Termux post-production
   │
   ├── voice
   ├── Whisper subtitles
   ├── music
   ├── sound effects
   └── FFmpeg
   │
   ▼
final.mp4
   │
   ▼
Telegram
```

Phone = orchestrator and post-production.
Kaggle = temporary heavy GPU worker, reached over a permanent ngrok static domain.
Do not assume Kaggle is a permanent server — it's a session you start manually each time.

## 3. Target Video

- Approximately 45–60 seconds
- 12–15 scenes
- Approximately 3–5 seconds per scene
- Vertical 9:16, 768×1344
- Consistent characters (achieved for images)
- Stable voice per character
- Narration/dialogue
- Sound effects
- Background music
- Animated subtitles
- Final MP4 returned through Telegram

## 4. Current Stack

### Android / Termux
- Termux
- Python 3.14
- FFmpeg 8.1.2

### AI / Cloud
- Gemini API — model `gemini-2.5-flash`
- Kaggle free GPU (T4), notebook: `kaggle.com/code/mrashish/vid-gen-kaggle`
- ngrok (free static domain) for exposing the Kaggle notebook to the internet

### Image Generation (Kaggle)
- Stable Diffusion XL base 1.0 (`stabilityai/stable-diffusion-xl-base-1.0`), fp16
- VAE fix: `madebyollin/sdxl-vae-fp16-fix` (stock fp16 VAE produces blank/blurry output — this fixes it)
- IP-Adapter (`h94/IP-Adapter`, `sdxl_models/ip-adapter_sdxl.bin`) for character consistency via a reference/anchor image
- FastAPI serving `/generate_image`, tunneled via ngrok

### Voice
- edge-tts, multi-voice (per-character)

### Video (planned)
- FFmpeg
- Stable Video Diffusion (SVD) for image-to-video — not yet implemented
- Whisper / faster-whisper for subtitles — not yet implemented

### Telegram
- python-telegram-bot

## 5. Current Project Structure

```
Vid_Gen/
├── bot.py
├── pipeline.py
├── director.py
├── tts.py
├── cloud_worker.py
├── assembler.py        (placeholder, empty)
├── subtitles.py         (placeholder, empty)
├── .env
├── test_story.json
├── jobs/
├── test_audio/
├── test_images/
├── output/
├── assets/
│   └── music/
├── kaggle_worker/
├── fonts/
└── README.md
```

## 6. Completed

### Environment
Verified: Python 3.14, pip, FFmpeg 8.1.2, and core packages (`telegram`, `edge_tts`, `requests`, `python-dotenv`) all working on Termux after the move from a laptop setup.

### Telegram Bot (`bot.py`)
Already exists and works. Loads `.env`, restricts access to the configured user ID, supports `/start` and `/video`, uses a render lock and `jobs/`, calls `build_video()`, sends the resulting video via Telegram, has error handling. Do not unnecessarily replace it.

### Gemini Director (`director.py`)
Converts a simple prompt into a structured story JSON via the Gemini API, using a strict JSON schema. Produces:
```
title
description
visual_style
characters[]   (id, name, role, age, appearance, clothing, personality, voice)
scenes[]       (id, duration, characters, narration, dialogue, visual_prompt, camera, sound_effects)
```
Designed for 12–15 sequential scenes with a stable character bible and stable per-character voice assignment (narrator/male/female/child mapped to fixed edge-tts voice IDs). Tested and working — produces `test_story.json`.

### Text-to-Speech (`tts.py`)
Uses edge-tts to generate one MP3 per narration line and per dialogue line, named `scene_NN_narrator.mp3` / `scene_NN_<character>_<n>.mp3`, using the voice map built from the story JSON's character voice fields. Verified valid via `ffprobe`/`ffmpeg` decode tests.

### Kaggle GPU Image Worker (`cloud_worker.py` + Kaggle notebook)
A Kaggle notebook (2 cells: one-time installs, then one merged cell for model load + FastAPI app + ngrok tunnel) runs:
- SDXL base 1.0 + the fp16-VAE fix, 30 steps, guidance 7.5 — produces clean, coherent 768×1344 images
- IP-Adapter loaded on top of the same pipeline for character consistency
- A `/generate_image` FastAPI endpoint accepting `prompt`, `width`, `height`, `steps`, `guidance`, `ip_scale`, and an optional `reference` image upload
- Exposed via ngrok using a free, permanently-assigned static domain (`*.ngrok-free.dev`), so the public URL never changes across notebook restarts — only needs to be set in `.env` once

`cloud_worker.py` on the Termux side:
- Generates one **anchor image** of the story's main character first (from their `appearance`/`clothing` fields)
- Sends that anchor as the `reference` image alongside every scene's `visual_prompt`, so IP-Adapter keeps the character visually consistent across all scenes
- Confirmed working end-to-end: 13/13 scenes generated successfully, character consistency visually confirmed across scenes 1, 7, and 13

**Notable issues hit and fixed along the way** (useful context if regenerating the notebook from scratch):
- SDXL-Turbo broke down at the 768×1344 vertical aspect ratio (duplicated limbs/heads) — it's only reliable near its trained resolution/step count; switched to full SDXL base with real steps.
- The stock SDXL base 1.0 fp16 VAE has a known numerical overflow bug causing blank/blurry/noisy output — fixed by loading `madebyollin/sdxl-vae-fp16-fix` instead.
- Once IP-Adapter is loaded, the pipeline requires an `ip_adapter_image` on every call — the anchor-generation call (no reference yet) needs a neutral placeholder image with `ip_scale=0.0` rather than omitting it, or it 500s.
- `cloudflared` quick tunnels are free but anonymous and get a new random URL every restart.
- ngrok's free plan no longer allows a custom-named static domain (that's paid-only) — but every free account is automatically given one pre-assigned static domain (found under the ngrok dashboard → Domains) that also never changes; use that instead of trying to choose a name.

## 7. Environment Variables (`.env`)

```
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
TELEGRAM_BOT_TOKEN=
ALLOWED_USER_ID=
KAGGLE_WORKER_URL=https://<your-assigned-domain>.ngrok-free.dev
```

The ngrok domain only needs to be set once — it stays the same across Kaggle session restarts. The Kaggle notebook itself stores its ngrok authtoken via Kaggle Secrets (`NGROK_AUTHTOKEN`), not in `.env` (the notebook and the phone are separate machines — `.env` only configures the Termux side).

Older pipeline code may also reference `POLLINATIONS_API_KEY` / `POLLINATIONS_MODEL` — Pollinations is fully replaced by the Kaggle GPU worker now.

## 8. Development Order / Status

```
DONE:
✅ Termux environment
✅ Project structure
✅ Telegram bot foundation
✅ Gemini Director → story JSON
✅ edge-tts multi-voice generation
✅ Kaggle GPU worker: SDXL base + VAE fix + FastAPI + ngrok static domain
✅ Character consistency via anchor image + IP-Adapter (confirmed visually)

NEXT:
⬜ Phase 7 — Image-to-video (Stable Video Diffusion), starting with a standalone
   test before wiring into cloud_worker.py — VRAM headroom and vertical-aspect
   quality on a free Kaggle T4 are both unproven yet
⬜ Scene MP4 download from Kaggle to Termux
⬜ Whisper subtitles (word-level timing → animated ASS captions)
⬜ Background music + sound effects in FFmpeg assembly
⬜ Final FFmpeg assembly (720×1280, 25fps, H.264/AAC)
⬜ Integrate everything into pipeline.py
⬜ End-to-end Telegram test: /video prompt → finished video, zero manual steps
```

## 9. Useful Commands

Project:
```
cd ~/AJ_projects/Vid_Gen
```

Director test:
```
python director.py "A little boy discovers a tiny magical door in his bedroom that leads to the moon"
```

TTS test:
```
python tts.py test_story.json test_audio
```

Image generation test (full story → per-scene consistent images):
```
python cloud_worker.py test_story.json test_images
```

MP3 validation:
```
ffprobe -v error -show_entries format=duration:stream=codec_name,sample_rate,channels -of default=noprint_wrappers=1 test_audio/scene_01_narrator.mp3
```

## 10. New-Chat Continuation Instructions

1. Read this README first.
2. Project path: `~/AJ_projects/Vid_Gen` (Termux, Python 3.14, FFmpeg 8.1.2).
3. Don't recreate `bot.py`, `director.py`, `tts.py`, or `cloud_worker.py` unless missing — all four are built and tested.
4. The Kaggle notebook (`vid-gen-kaggle`) needs to be manually started each session — it is not a permanent server. Re-run its cells top to bottom; the public URL (ngrok static domain) stays the same, so `.env` does not need updating between sessions.
5. The next major task is Phase 7: image-to-video with Stable Video Diffusion. Plan is to test SVD standalone in the Kaggle notebook first (prove VRAM/quality work) before wiring a `/generate_video` endpoint into the same server.
6. Keep heavy AI generation off the Android device — Termux stays lightweight (orchestration, TTS, downloading, subtitles, FFmpeg only).
7. Keep the system free/free-tier where practical.

## 11. One-Line Goal

```
Telegram prompt → Gemini Director → consistent AI character images + voices (DONE) → Kaggle GPU video generation (NEXT) → Whisper subtitles + FFmpeg → final vertical video → Telegram
```
