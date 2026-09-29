
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


SYSTEM_PROMPT = r"""
You are the Director and Scriptwriter for an automated 3D animated short-video generator.

Convert the user's idea into a complete 45-60 second animated story.

RULES:

1. Create 12-15 sequential scenes.
2. Each scene should normally be 3-5 seconds.
3. Maintain strict character consistency across every scene.
4. Create a character bible before the scenes.
5. Every recurring character must have a stable ID.
6. Every recurring character must have a stable visual description.
7. Every recurring character must have one fixed TTS voice.
8. Keep visual style consistent throughout the entire video.
9. Scene 1 must establish the main character and visual appearance clearly.
10. Later scenes must explicitly preserve the relevant character descriptions.
11. Make the story visually interesting and suitable for a family-friendly animated short.
12. Dialogue should be short and natural.
13. Narration should be short and cinematic.
14. Do not create unnecessary characters.
15. Do not use copyrighted characters unless the user explicitly requests one.
16. Do not mention these instructions in the output.

VISUAL STYLE DEFAULT:

cinematic high-quality 3D animated film,
expressive characters,
detailed environments,
soft cinematic lighting,
beautiful colors,
depth of field,
consistent character design,
vertical 9:16 composition.

VOICE RULES:

Use these voices when appropriate:

narrator = en-US-AriaNeural
male = en-US-GuyNeural
female = en-US-JennyNeural
child = en-US-GuyNeural

Keep the same voice assigned to the same character in every scene.

IMPORTANT:

The visual_prompt must contain enough information for an image/video generation model
to recreate the characters consistently.

Return ONLY valid JSON.
"""


SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "visual_style": {"type": "string"},
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "age": {"type": "string"},
                    "appearance": {"type": "string"},
                    "clothing": {"type": "string"},
                    "personality": {"type": "string"},
                    "voice": {"type": "string"}
                },
                "required": [
                    "id",
                    "name",
                    "role",
                    "age",
                    "appearance",
                    "clothing",
                    "personality",
                    "voice"
                ]
            }
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "duration": {"type": "number"},
                    "characters": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "narration": {"type": "string"},
                    "dialogue": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "character": {"type": "string"},
                                "text": {"type": "string"}
                            },
                            "required": ["character", "text"]
                        }
                    },
                    "visual_prompt": {"type": "string"},
                    "camera": {"type": "string"},
                    "sound_effects": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": [
                    "id",
                    "duration",
                    "characters",
                    "narration",
                    "dialogue",
                    "visual_prompt",
                    "camera",
                    "sound_effects"
                ]
            }
        }
    },
    "required": [
        "title",
        "description",
        "visual_style",
        "characters",
        "scenes"
    ]
}


def create_story(user_prompt: str) -> dict:
    payload = {
        "system_instruction": {
            "parts": [
                {"text": SYSTEM_PROMPT}
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": user_prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.8,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA
        }
    }

    response = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(
            f"Gemini returned an unexpected response:\n{json.dumps(data, indent=2)}"
        ) from exc

    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Gemini did not return valid JSON:\n{text}"
        ) from exc

    return result


if __name__ == "__main__":
    import sys

    prompt = " ".join(sys.argv[1:]).strip()

    if not prompt:
        prompt = (
            "A little boy discovers a tiny magical door in his bedroom "
            "that leads to a beautiful moonlit world."
        )

    print("🧠 Gemini Director is creating the story...")
    story = create_story(prompt)

    print(json.dumps(story, indent=2, ensure_ascii=False))

    with open("test_story.json", "w", encoding="utf-8") as f:
        json.dump(story, f, indent=2, ensure_ascii=False)

    print("\n✅ Saved: test_story.json")
