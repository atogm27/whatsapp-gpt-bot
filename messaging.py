from dataclasses import dataclass
from typing import Any


@dataclass
class IncomingMessage:
    sender: str
    type: str
    text: str | None = None
    media_id: str | None = None


def extract_incoming_message(payload: dict[str, Any]) -> IncomingMessage | None:
    """Obtiene el primer mensaje del webhook de forma segura."""

    entries = payload.get("entry") or []
    if not entries:
        return None

    entry = entries[0] or {}
    changes = entry.get("changes") or []
    if not changes:
        return None

    change = changes[0] or {}
    value = change.get("value") or {}
    messages = value.get("messages") or []
    if not messages:
        return None

    msg = messages[0]
    msg_type = msg.get("type", "text")

    text_body = None
    if msg_type == "text":
        text_obj = msg.get("text") or {}
        text_body = text_obj.get("body")

    media_id = None
    if msg_type in {"audio", "voice"}:
        media_obj = msg.get(msg_type) or {}
        media_id = media_obj.get("id")

    return IncomingMessage(
        sender=msg.get("from", ""),
        type=msg_type,
        text=text_body,
        media_id=media_id,
    )
