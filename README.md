# Vid_Gen — Free AI Video Generator

AI video automation project running from Android Termux, with Gemini as the Director/Scriptwriter, edge-tts for voice generation, and Kaggle GPU as the heavy video-rendering worker.

Goal:

Telegram `/video <prompt>` → Gemini story → AI voices + GPU-rendered scenes → subtitles + FFmpeg → final vertical MP4 → Telegram.

## 1. Project Location

Main Termux workspace:

```text
/data/data/com.termux/files/home/AJ_projects/
```

Current project:

```text
/data/data/com.termux/files/home/AJ_projects/Vid_Gen
```

Equivalent Termux shortcut:

```bash
cd ~/AJ_projects/Vid_Gen
```

`~` means:

```text
/data/data/com.termux/files/home
```

For scripts/automation, use the full path if needed:

```python
PROJECT_DIR = "/data/data/com.termux/files/home/AJ_projects/Vid_Gen"
```

## 2. Target Architecture

```text
Telegram
   │
   │ /video <prompt>
   ▼
Android / Termux
   │
   ├── bot.py
   ├── director.py
   ├── tts.py
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
Kaggle GPU Worker
   │
   ├── anchor/reference image
   ├── scene images
   └── image → video
   │
   ▼
scene MP4s
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

Kaggle = temporary heavy GPU worker.

Do not assume Kaggle is a permanent server.

## 3. Target Video

- Approximately 45–60 seconds
- 12–15 scenes
- Approximately 3–5 seconds per scene
- Vertical 9:16
- 720 × 1280
- 25 FPS
- 3D animated/cinematic style
- Consistent characters
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

- Gemini API
- Target Gemini model: `gemini-2.5-flash`
- Kaggle free GPU
- Google Colab as backup

### Voice

- edge-tts

### Video

- FFmpeg
- AI image generation on Kaggle
- Image-to-video model on Kaggle
- Whisper / faster-whisper / whisper.cpp for subtitles

### Telegram

- python-telegram-bot

## 5. Current Project Structure

```text
Vid_Gen/
├── bot.py
├── pipeline.py
├── director.py
├── tts.py
├── .env
├── test_story.json
├── jobs/
├── test_audio/
├── output/
├── assets/
│   └── music/
├── kaggle_worker/
└── README.md
```

## 6. Completed

### Environment

Verified:

```text
Python 3.14
pip 26.1.2
FFmpeg 8.1.2
```

Verified Python packages:

```text
telegram
edge_tts
requests
python-dotenv
```

Verification command:

```bash
python -c "import telegram, edge_tts, requests, dotenv; print('All current packages OK')"
```

### Telegram Bot

`bot.py` already exists and works.

It:

- Loads `.env` before importing `pipeline`
- Uses the Telegram bot token
- Restricts access to the configured user ID
- Supports `/start`
- Supports `/video`
- Uses `jobs/`
- Uses a render lock
- Calls `build_video()`
- Sends the resulting video with Telegram
- Has error handling

Do not unnecessarily replace the working `bot.py`.

### Gemini Director

File:

```text
director.py
```

Purpose:

Convert a simple user prompt into structured video JSON.

Example:

```bash
python director.py "A little boy discovers a tiny magical door in his bedroom that leads to the moon"
```

Successfully generated:

```text
test_story.json
```

Director JSON contains:

```text
title
description
visual_style
characters
scenes
```

Character fields:

```text
id
name
role
age
appearance
clothing
personality
voice
```

Scene fields:

```text
id
duration
characters
narration
dialogue
visual_prompt
camera
sound_effects
```

The Director is designed for:

- 12–15 sequential scenes
- Stable character IDs
- Stable visual descriptions
- Consistent clothing/hair/appearance
- Stable voices
- Family-friendly content
- Vertical 9:16 video
- Valid JSON output

### Text-to-Speech

File:

```text
tts.py
```

Uses:

```text
edge-tts
```

Creates per-scene MP3 files such as:

```text
test_audio/
├── scene_01_narrator.mp3
├── scene_01_<character>_1.mp3
├── scene_02_narrator.mp3
└── ...
```

Narrator default:

```text
en-US-AriaNeural
```

Character voice selection can be improved later.

### Audio Verification

The generated MP3 has already been verified.

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,sample_rate,channels -of default=noprint_wrappers=1 test_audio/scene_01_narrator.mp3
```

And:

```bash
ffmpeg -v error -i test_audio/scene_01_narrator.mp3 -f null -
```

Both completed without errors.

Therefore the generated MP3 is valid and usable by the video pipeline.

### Android Playback

Android playback through `termux-open` was tested but did not work.

This is intentionally NOT a blocker.

Do not spend time troubleshooting MP3/WAV playback unless needed later.

Important verification:

```text
edge-tts → MP3 → FFmpeg decode = SUCCESS
```

The final video does not require Termux to play the MP3.

## 7. Android Storage Note

The project lives inside Termux private storage:

```text
/data/data/com.termux/files/home/AJ_projects/Vid_Gen
```

Android's normal Files app may not browse this location.

Shared Android storage is normally available through:

```text
~/storage/
```

after:

```bash
termux-setup-storage
```

Keep the actual project under:

```text
~/AJ_projects/Vid_Gen
```

## 8. Environment Variables

`.env` contains secrets/configuration.

Important variables include:

```text
GEMINI_API_KEY
GEMINI_MODEL
VOICE
TTS_RATE
TELEGRAM_BOT_TOKEN
ALLOWED_USER_ID
```

Older pipeline code may also contain:

```text
POLLINATIONS_API_KEY
POLLINATIONS_MODEL
```

Pollinations belongs to the old pipeline and is being replaced by the Kaggle GPU worker.

Never expose `.env` or API keys publicly.

## 9. Old vs New Pipeline

Old:

```text
Telegram
 ↓
Gemini
 ↓
Pollinations image generation
 ↓
edge-tts
 ↓
FFmpeg
 ↓
final.mp4
```

New:

```text
Telegram
 ↓
Gemini Director
 ↓
story JSON
 ├───────────────┐
 ▼               ▼
edge-tts       Kaggle GPU
voice           │
                ├── image generation
                └── image-to-video
                │
                ▼
             scene MP4s
                │
                ▼
          Termux post-production
                │
       ┌────────┼─────────┐
       ▼        ▼         ▼
     voice   subtitles   music
                │
                ▼
              FFmpeg
                │
                ▼
            final.mp4
```

Useful FFmpeg code from the old `pipeline.py` should be reused where practical instead of rewriting everything.

## 10. Next Major Step — Kaggle GPU Worker

This is the next task.

Create a Kaggle notebook that acts as a temporary GPU worker.

Concept:

```text
Termux
   │
   │ story JSON
   ▼
Kaggle GPU session
   │
   ├── generate anchor image
   ├── generate scene images
   ├── image-to-video
   ├── render MP4 clips
   │
   ▼
download scene MP4s
   │
   ▼
Termux
```

Primary:

```text
Kaggle
```

Backup:

```text
Google Colab
```

Do not install large GPU AI libraries on Termux.

## 11. Planned Rendering

Candidate models to evaluate on Kaggle:

```text
FLUX.1-schnell
SDXL
Stable Video Diffusion
AnimateDiff
```

Choose based on:

- Kaggle GPU/VRAM
- Installation reliability
- Speed
- Consistency
- Free/open-source availability

Do not assume a model works on Kaggle until tested.

## 12. Character Consistency

Character consistency is a major requirement.

Example anchor description:

```text
3D animated style, 2-year-old toddler,
curly brown hair, blue-white striped shirt,
warm kitchen lighting
```

Important character details should remain consistent:

```text
character ID
appearance
clothing
hair
age
visual style
```

Use reference/anchor images wherever supported.

## 13. Voice Consistency

Each character gets a stable voice.

Example:

```text
narrator → en-US-AriaNeural
boy → fixed selected voice
mother → fixed selected voice
```

A character should not randomly change voices between scenes.

## 14. Subtitle System

Planned:

```text
Whisper
   ↓
timestamps
   ↓
ASS subtitles
   ↓
FFmpeg
```

Potential implementation:

```text
faster-whisper
```

or:

```text
whisper.cpp
```

## 15. Final Video

Target:

```text
720x1280
25 FPS
9:16
~45–60 seconds
```

Final:

```text
output/final.mp4
```

FFmpeg combines:

```text
scene videos
+
voice
+
dialogue
+
background music
+
sound effects
+
subtitles
```

## 16. Final Telegram Experience

Desired flow:

```text
User:
 /video A little robot finds a magical forest

Bot:
Generating story...

Bot:
Creating voices...

Bot:
Rendering scenes...

Bot:
Assembling video...

Bot:
[final.mp4]
```

## 17. Resource Rules

- Keep local Termux lightweight.
- Do not render heavy AI video locally on the phone.
- Kaggle/Colab handles GPU work.
- Termux handles orchestration, TTS, downloading, subtitles and FFmpeg.
- Avoid unnecessary Docker.
- Prefer free/open-source/free-tier services.
- Do not add paid services unless explicitly decided later.

## 18. Development Order

Build and test each boundary:

```text
Gemini JSON
   ↓
Voice MP3
   ↓
Kaggle image
   ↓
Kaggle video
   ↓
Download scene
   ↓
Whisper subtitles
   ↓
FFmpeg assembly
   ↓
Telegram delivery
```

Do not build the entire system blindly before testing each major boundary.

## 19. Current Status

```text
DONE:
✅ Termux environment
✅ Project structure
✅ Telegram bot foundation
✅ Gemini Director
✅ Story JSON
✅ edge-tts
✅ Voice MP3 generation
✅ MP3 validation

NEXT:
⬜ Kaggle worker
⬜ GPU image generation
⬜ Anchor/reference image
⬜ Image-to-video
⬜ Scene MP4 download
⬜ Whisper subtitles
⬜ Background music
⬜ Final FFmpeg assembly
⬜ Integrate new pipeline.py
⬜ End-to-end Telegram test
```

## 20. Useful Commands

Project:

```bash
cd /data/data/com.termux/files/home/AJ_projects/Vid_Gen
```

or:

```bash
cd ~/AJ_projects/Vid_Gen
```

Python:

```bash
python --version
```

FFmpeg:

```bash
ffmpeg -version | head -n 1
```

Director test:

```bash
python director.py "A little boy discovers a tiny magical door in his bedroom that leads to the moon"
```

TTS test:

```bash
python tts.py
```

MP3 validation:

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,sample_rate,channels -of default=noprint_wrappers=1 test_audio/scene_01_narrator.mp3
```

MP3 decode test:

```bash
ffmpeg -v error -i test_audio/scene_01_narrator.mp3 -f null -
```

## 21. New-Chat Continuation Instructions

When continuing this project in a new ChatGPT conversation:

1. Read this README first.
2. Current project path is:

```text
/data/data/com.termux/files/home/AJ_projects/Vid_Gen
```

3. Do not recreate `director.py` unless missing.
4. Do not recreate `tts.py` unless missing.
5. Do not replace the working `bot.py` unnecessarily.
6. MP3 generation is already tested successfully.
7. Android MP3/WAV playback is intentionally skipped.
8. The next major task is the Kaggle GPU worker.
9. Kaggle is a temporary GPU worker, not a permanent server.
10. Keep the system free/free-tier where practical.
11. Keep heavy AI generation off the Android device.

## 22. One-Line Goal

```text
Telegram prompt → Gemini Director → consistent 3D scenes + AI voices → Kaggle GPU video generation → Whisper subtitles + FFmpeg → final vertical video → Telegram
```
