"""Optional voice. ElevenLabs only runs when someone asks, and only then does the eulogy leave the machine."""

from __future__ import annotations

import os

import httpx


class VoiceError(RuntimeError):
    pass


def elevenlabs_configured() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY", "").strip())


def _pick_voice(client: httpx.Client) -> str:
    chosen = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if chosen:
        return chosen
    response = client.get("https://api.elevenlabs.io/v1/voices")
    response.raise_for_status()
    voices = response.json().get("voices") or []
    if not voices:
        raise VoiceError("ElevenLabs returned no voices for this key.")
    for voice in voices:
        label = f"{voice.get('name', '')} {voice.get('description', '')}".lower()
        if any(word in label for word in ("whisper", "soft", "ghost", "narrat")):
            return voice["voice_id"]
    return voices[0]["voice_id"]


def synthesize(text: str) -> tuple[bytes, str]:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise VoiceError("Set ELEVENLABS_API_KEY to send the eulogy to ElevenLabs. Otherwise the browser can speak it locally.")
    spoken = " ".join(text.split())
    if len(spoken) > 1500:
        spoken = spoken[:1500]
    headers = {"xi-api-key": key, "Accept": "audio/mpeg"}
    try:
        with httpx.Client(headers=headers, timeout=60.0) as client:
            voice_id = _pick_voice(client)
            response = client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                json={
                    "text": spoken,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.35, "similarity_boost": 0.75, "style": 0.15},
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise VoiceError(f"ElevenLabs did not return audio: {exc}") from exc
    if not response.content:
        raise VoiceError("ElevenLabs returned an empty recording.")
    return response.content, voice_id
