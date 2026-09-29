

import asyncio
import json
import sys
from pathlib import Path

import edge_tts


DEFAULT_NARRATOR = "en-US-AriaNeural"


async def generate_voice(
    text: str,
    voice: str,
    output: Path,
    rate: str = "+0%",
):
    """Generate one MP3 using Microsoft Edge neural TTS."""
    if not text.strip():
        return

    output.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
    )

    await communicate.save(str(output))


def build_voice_map(story: dict) -> dict:
    """Create character_id -> voice mapping."""

    voices = {
        "narrator": DEFAULT_NARRATOR
    }

    for character in story.get("characters", []):
        char_id = character["id"]
        voice = character.get("voice") or DEFAULT_NARRATOR
        voices[char_id] = voice

    return voices


async def generate_story_audio(
    story: dict,
    output_dir: Path,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    voice_map = build_voice_map(story)

    print("\n🎙️ Voice assignments:")

    for character_id, voice in voice_map.items():
        print(f"   {character_id} → {voice}")

    print()

    for scene in story.get("scenes", []):
        scene_id = int(scene["id"])

        # ----------------------------
        # Narration
        # ----------------------------

        narration = scene.get("narration", "").strip()

        if narration:
            output = output_dir / f"scene_{scene_id:02d}_narrator.mp3"

            print(
                f"🎙️ Scene {scene_id}: narrator"
            )

            await generate_voice(
                narration,
                DEFAULT_NARRATOR,
                output,
            )

        # ----------------------------
        # Dialogue
        # ----------------------------

        dialogue = scene.get("dialogue", [])

        for index, line in enumerate(dialogue, start=1):

            character_id = line.get("character", "").strip()
            text = line.get("text", "").strip()

            if not text:
                continue

            voice = voice_map.get(
                character_id,
                DEFAULT_NARRATOR,
            )

            output = (
                output_dir
                / f"scene_{scene_id:02d}_{character_id}_{index}.mp3"
            )

            print(
                f"🗣️ Scene {scene_id}: "
                f"{character_id} → {voice}"
            )

            await generate_voice(
                text,
                voice,
                output,
            )

    print("\n✅ All voice files generated.")


def main():

    story_file = Path(
        sys.argv[1] if len(sys.argv) > 1 else "test_story.json"
    )

    output_dir = Path(
        sys.argv[2] if len(sys.argv) > 2 else "test_audio"
    )

    if not story_file.exists():
        raise FileNotFoundError(
            f"Story file not found: {story_file}"
        )

    with open(
        story_file,
        "r",
        encoding="utf-8",
    ) as f:
        story = json.load(f)

    asyncio.run(
        generate_story_audio(
            story,
            output_dir,
        )
    )


if __name__ == "__main__":
    main()

