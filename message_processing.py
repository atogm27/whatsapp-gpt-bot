from audio import transcribir_audio
from messaging import IncomingMessage
from whatsapp import download_media


class MessageProcessingError(Exception):
    """Error controlado al intentar extraer el contenido útil del mensaje."""

    def __init__(self, user_message: str, status: str):
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


async def resolve_message_text(message: IncomingMessage) -> str:
    """Devuelve el texto final del mensaje, manejando texto plano y audios."""

    if message.type == "text":
        if message.text:
            clean_text = message.text.strip()
            if clean_text:
                return clean_text
        raise MessageProcessingError(
            "No recibí contenido para procesar. ¿Podrías enviarlo de nuevo?",
            "empty_text",
        )

    if message.type in {"audio", "voice"}:
        if not message.media_id:
            raise MessageProcessingError(
                "No pude obtener el audio, ¿puedes intentarlo otra vez?",
                "no_audio_id",
            )

        try:
            audio_bytes, mime_type = await download_media(message.media_id)
            transcription = await transcribir_audio(audio_bytes, mime_type)
        except Exception as exc:  # noqa: BLE001 - queremos registrar cualquier error
            raise MessageProcessingError(
                "Hubo un problema descargando tu audio. ¿Puedes enviarlo nuevamente?",
                "audio_download_error",
            ) from exc

        if transcription:
            text = transcription.strip()
            if text:
                print("📝 Transcripción obtenida:", text)
                return text

        raise MessageProcessingError(
            "No pude transcribir tu audio. ¿Podrías intentarlo con otro mensaje?",
            "transcription_failed",
        )

    raise MessageProcessingError(
        "Por ahora solo puedo ayudarte con mensajes de texto o audios. 😊",
        "unsupported_type",
    )
