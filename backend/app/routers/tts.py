"""Text-to-speech proxy for the video explainer narration.

Synthesises narration with Azure Speech (part of the same Azure AI Foundry
account) and streams MP3 back to the browser. Keeping the key server-side means
it is never exposed to the client.
"""
from __future__ import annotations

import logging
from html import escape

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..config import get_settings
from ..models import User

logger = logging.getLogger("githubiq.tts")
router = APIRouter(prefix="/api", tags=["tts"])


class TTSRequest(BaseModel):
    text: str = Field(..., max_length=3000)
    voice: str = ""


@router.get("/tts/config")
def tts_config() -> dict:
    return {"available": get_settings().speech_configured}


@router.post("/tts")
def synthesize(req: TTSRequest, _user: User = Depends(get_current_user)) -> Response:
    settings = get_settings()
    if not settings.speech_configured:
        raise HTTPException(status_code=503, detail="Speech is not configured")

    voice = req.voice or settings.speech_voice
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="en-US"><voice name="{escape(voice)}">'
        f'<prosody rate="+6%">{escape(req.text)}</prosody></voice></speak>'
    )
    url = f"https://{settings.speech_region}.tts.speech.microsoft.com/cognitiveservices/v1"
    try:
        resp = httpx.post(
            url,
            headers={
                "Ocp-Apim-Subscription-Key": settings.speech_api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "githubiq",
            },
            content=ssml.encode("utf-8"),
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("TTS failed: %s", exc)
        raise HTTPException(status_code=502, detail="Speech synthesis failed") from exc

    return Response(
        content=resp.content,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
