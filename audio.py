import io

from settings import OPENAI_TRANSCRIBE_MODEL, client


def _extension_from_mime(mime_type: str) -> str:
    if not mime_type:
        return "mp3"
    if "wav" in mime_type:
        return "wav"
    if "ogg" in mime_type:
        return "ogg"
    if "m4a" in mime_type:
        return "m4a"
    return "mp3"


async def transcribir_audio(audio_bytes: bytes, mime_type: str | None = None) -> str | None:
    """Envía el audio al endpoint de OpenAI y devuelve el texto transcrito."""

    ext = _extension_from_mime(mime_type or "")
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = f"audio.{ext}"

    try:
        transcription = client.audio.transcriptions.create(
            model=OPENAI_TRANSCRIBE_MODEL,
            file=audio_file,
            response_format="text",
        )
    except Exception as exc:
        print("❌ Error transcribiendo audio:", exc)
        return None

    if isinstance(transcription, str):
        return transcription.strip()

    text = getattr(transcription, "text", "")
    return text.strip() if text else None
