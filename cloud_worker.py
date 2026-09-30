import os
import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

WORKER_URL = os.environ["KAGGLE_WORKER_URL"].rstrip("/")


def _post_generate(
    prompt: str,
    output: Path,
    width: int = 768,
    height: int = 1344,
    steps: int = 30,
    guidance: float = 7.5,
    ip_scale: float = 0.6,
    reference_bytes: bytes = None,
) -> bytes:
    output.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "prompt": prompt,
        "width": str(width),
        "height": str(height),
        "steps": str(steps),
        "guidance": str(guidance),
        "ip_scale": str(ip_scale),
    }

    files = None
    if reference_bytes is not None:
        files = {"reference": ("anchor.png", reference_bytes, "image/png")}

    response = requests.post(
        f"{WORKER_URL}/generate_image",
        data=data,
        files=files,
        timeout=180,
    )
    response.raise_for_status()

    with open(output, "wb") as f:
        f.write(response.content)

    return response.content


def generate_anchor_image(story: dict, output_dir: Path) -> bytes:
    visual_style = story.get("visual_style", "")
    characters = story.get("characters", [])

    if not characters:
        raise ValueError("Story has no characters to anchor on")

    protagonist = characters[0]
    prompt = (
        f"{protagonist.get('appearance', '')}, wearing {protagonist.get('clothing', '')}, "
        f"character portrait, {visual_style}"
    ).strip(", ")

    output = output_dir / "anchor.png"
    print(f"🧑 Generating anchor image for '{protagonist.get('name', protagonist.get('id'))}'...")

    anchor_bytes = _post_generate(prompt, output)
    print(f"✅ Anchor saved: {output}")

    return anchor_bytes


def generate_story_images(story: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    visual_style = story.get("visual_style", "")
    anchor_bytes = generate_anchor_image(story, output_dir)

    for scene in story.get("scenes", []):
        scene_id = int(scene["id"])
        visual_prompt = scene.get("visual_prompt", "").strip()

        if not visual_prompt:
            print(f"⚠️ Scene {scene_id}: no visual_prompt, skipping")
            continue

        full_prompt = f"{visual_prompt}, {visual_style}".strip(", ")
        output = output_dir / f"scene_{scene_id:02d}.png"

        print(f"🎨 Scene {scene_id}: generating image...")
        _post_generate(full_prompt, output, reference_bytes=anchor_bytes)
        print(f"✅ Scene {scene_id}: saved {output}")

    print("\n✅ All scene images generated.")


def main():
    story_file = Path(sys.argv[1] if len(sys.argv) > 1 else "test_story.json")
    output_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "test_images")

    if not story_file.exists():
        raise FileNotFoundError(f"Story file not found: {story_file}")

    with open(story_file, "r", encoding="utf-8") as f:
        story = json.load(f)

    generate_story_images(story, output_dir)


if __name__ == "__main__":
    main()


