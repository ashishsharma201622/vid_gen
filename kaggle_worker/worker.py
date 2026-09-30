from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Vid_Gen GPU Worker")


class SceneRequest(BaseModel):
    scene_id: str
    duration: float
    visual_prompt: str
    reference_image: Optional[str] = None
    audio_path: Optional[str] = None


@app.get("/")
def root():
    return {
        "status": "ok",
        "worker": "vid_gen",
        "message": "Kaggle GPU worker is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.post("/render")
def render_scene(scene: SceneRequest):
    return {
        "status": "queued",
        "scene_id": scene.scene_id,
        "message": "Scene received by GPU worker"
    }



