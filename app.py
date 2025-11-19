import io
import os
import json
from typing import cast  # 👈 CAMBIO
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import httpx
from openai import OpenAI
from openai.types.chat import (         # 👈 CAMBIO
    ChatCompletionMessageToolCall,
    ChatCompletionToolParam,
)

# ====================================================
# 0) CONSTANTES DE PROMPTS
# ====================================================

PROMPT_CON_ERROR = """
Eres un tutor experto del idioma {language}.
Debes responder siempre en {language}.

1) Corrige suavemente el texto del usuario (gramática, vocabulario, estilo).
2) Explica brevemente en español los errores más importantes y la regla básica. 
   Que quede claro el error que hay que corregir.
3) Responde en {language} de forma natural, como en una conversación 
   para seguir la conversación del alumno.

No seas excesivamente extenso. Sé amable, motivador y fomenta que el usuario siga practicando.
Intenta que la conversación sea agradable y amena. Interésate por cualquier gusto que parezca tener.

Ejemplo:

It's great to hear that you're finding time for personal activities even after a busy day! 
What kind of stuff are you working on for yourself? Is it a hobby or something else?

Frase corregida: <Not too much here either. I've been working all day, and now I'm doing some stuff for myself.>

En tu texto, el cambio principal es el uso de contracciones ("I'm" en lugar de "im")
y la corrección de la frase para que suene más natural en inglés. 
También es importante usar "myself" en lugar de "my own" para referirse a hacer cosas 
para uno mismo. En inglés, es común usar la forma reflexiva "myself" después de verbos 
como "doing".
"""

PROMPT_SIN_ERROR = """
Eres un hablante del idioma {language}.

Tu tarea es:
Responder en {language} de forma natural, como en una conversación 
para seguir la conversación del alumno.

No reescribas el texto del usuario ni señales errores,
salvo que él lo pida explícitamente.

Sé amable, motivador y fomenta que el usuario siga practicando.
Intenta que la conversación sea agradable y amena.
Interésate por cualquier gusto que parezca tener.
"""

# ====================================================
# 0.b) CONSTANTES DE TOOLS (FUNCTION CALLING)
# ====================================================

LANGUAGE_TOOL: ChatCompletionToolParam = {  # 👈 CAMBIO: tipo explícito
    "type": "function",
    "function": {
        "name": "clasificar_mensaje",
        "description": "Detecta el idioma predominante del mensaje del usuario.",
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": (
                        "Idioma detectado, por ejemplo: español, inglés, alemán, "
                        "francés, italiano, japonés, portugués, etc."
                    ),
                }
            },
            "required": ["language"],
        },
    },
}

ERRORS_TOOL: ChatCompletionToolParam = {  # 👈 CAMBIO: tipo explícito
    "type": "function",
    "function": {
        "name": "evaluar_errores",
        "description": (
            "Evalúa si el texto del usuario en el idioma indicado contiene "
            "errores gramaticales, de vocabulario u ortografía que merezca la pena corregir."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "has_errors": {
                    "type": "boolean",
                    "description": (
                        "true si el texto tiene errores relevantes que conviene corregir; "
                        "false si el texto es correcto o solo tiene detalles menores."
                    ),
                },
                "severity": {
                    "type": "string",
                    "description": "Grado aproximado de error en el texto.",
                    "enum": ["ninguno", "leve", "moderado", "alto"],
                },
            },
            "required": ["has_errors"],
        },
    },
}

# ====================================================
# APP Y CONFIG
# ====================================================

app = FastAPI()

# ====== VARIABLES DE ENTORNO ======
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "")
WA_TOKEN = os.environ.get("WA_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TRANSCRIBE_MODEL = os.environ.get(
    "OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"
)

if not VERIFY_TOKEN:
    print("⚠️ Falta VERIFY_TOKEN")
if not WA_PHONE_ID:
    print("⚠️ Falta WA_PHONE_ID")
if not WA_TOKEN:
    print("⚠️ Falta WA_TOKEN")
if not OPENAI_API_KEY:
    print("⚠️ Falta OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
GRAPH_URL = f"https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages"


# ====================================================
# 1) VERIFICACIÓN DEL WEBHOOK (GET)
# ====================================================
@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")

    return PlainTextResponse("error: invalid token", status_code=403)


# ====================================================
# 2) FUNCIÓN PARA ENVIAR MENSAJES A WHATSAPP
# ====================================================
async def send_text(to: str, body: str):
    """Envía un mensaje de texto al usuario por WhatsApp Cloud API."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }

    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client_http:
        r = await client_http.post(GRAPH_URL, headers=headers, json=payload)
        print("📤 Respuesta de WhatsApp:", r.status_code, r.text)
        r.raise_for_status()


# ====================================================
# 2.b) DESCARGA DE MEDIOS (AUDIOS)
# ====================================================
async def download_media(media_id: str):
    """Descarga el binario del medio y su MIME type a partir de su media_id."""

    headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    base_url = "https://graph.facebook.com/v20.0"

    async with httpx.AsyncClient(timeout=30) as client_http:
        meta_resp = await client_http.get(
            f"{base_url}/{media_id}",
            headers=headers,
        )
        print("ℹ️ Respuesta metadata media:", meta_resp.status_code, meta_resp.text)
        meta_resp.raise_for_status()

        meta_data = meta_resp.json()
        media_url = meta_data.get("url")
        mime_type = meta_data.get("mime_type", "")

        if not media_url:
            raise ValueError("No se pudo obtener la URL del audio")

        media_resp = await client_http.get(media_url, headers=headers)
        print("🎧 Descarga de audio:", media_resp.status_code)
        media_resp.raise_for_status()

        return media_resp.content, mime_type


# ====================================================
# 2.c) TRANSCRIPCIÓN DE AUDIOS
# ====================================================
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


# ====================================================
# 3) FUNCIÓN PARA DETECTAR EL IDIOMA DEL MENSAJE
# ====================================================
async def detectar_idioma(text: str) -> str:
    res = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu única tarea es detectar el idioma del mensaje "
                    "y devolverlo mediante la función 'clasificar_mensaje'. "
                    "No añadas texto adicional."
                ),
            },
            {"role": "user", "content": text},
        ],
        tools=[LANGUAGE_TOOL],
        tool_choice="auto",
    )

    tool_calls = res.choices[0].message.tool_calls or []  # 👈 CAMBIO: or []
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al detectar idioma:", res)
        return "desconocido"

    # 👇 CAMBIO: casteamos a ChatCompletionMessageToolCall para que el type checker sepa que tiene `.function`
    tool_call = cast(ChatCompletionMessageToolCall, tool_calls[0])
    args_json = tool_call.function.arguments
    args = json.loads(args_json)

    language = args.get("language", "desconocido")
    return language


# ====================================================
# 3.b) FUNCIÓN PARA EVALUAR SI HAY ERRORES QUE CORREGIR
# ====================================================
async def evaluar_errores(text: str, language: str):
    """
    Devuelve:
      has_errors: bool -> True si merece la pena corregir, False si el texto está bien.
      severity: str    -> 'ninguno', 'leve', 'moderado', 'alto'
    """
    res = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente que evalúa textos. "
                    "Tu tarea es SOLO decidir si el mensaje del usuario en el idioma indicado "
                    f"({language}) tiene errores gramaticales, de vocabulario u ortográficos "
                    "lo suficientemente relevantes como para que un profesor los corrija. "
                    "No corrijas el texto, no des ejemplos, no des explicaciones. "
                    "Devuelve únicamente el resultado mediante la función 'evaluar_errores'."
                ),
            },
            {"role": "user", "content": text},
        ],
        tools=[ERRORS_TOOL],
        tool_choice="auto",
        temperature=0,
    )

    tool_calls = res.choices[0].message.tool_calls or []  # 👈 CAMBIO
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al evaluar errores:", res)
        return False, "ninguno"

    tool_call = cast(ChatCompletionMessageToolCall, tool_calls[0])  # 👈 CAMBIO
    args_json = tool_call.function.arguments
    args = json.loads(args_json)

    has_errors = bool(args.get("has_errors", False))
    severity = args.get("severity", "ninguno")

    return has_errors, severity


# ====================================================
# 4) WEBHOOK PRINCIPAL (POST)
# ====================================================
@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    print("📩 Webhook recibido:", json.dumps(data, indent=2, ensure_ascii=False))

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "no_messages"}

        msg = messages[0]
        from_id = msg["from"]

        # === obtener el texto o transcribir audio ===
        msg_type = msg.get("type", "text")
        text = None

        if msg_type == "text":
            text_obj = msg.get("text")
            if text_obj and text_obj.get("body"):
                text = text_obj.get("body").strip()
        elif msg_type in {"audio", "voice"}:
            media_obj = msg.get(msg_type) or {}
            media_id = media_obj.get("id")
            if not media_id:
                await send_text(from_id, "No pude obtener el audio, ¿puedes intentarlo otra vez?")
                return {"status": "no_audio_id"}

            try:
                audio_bytes, mime_type = await download_media(media_id)
                transcription = await transcribir_audio(audio_bytes, mime_type)
            except Exception as exc:
                print("❌ Error descargando audio:", exc)
                await send_text(
                    from_id,
                    "Hubo un problema descargando tu audio. ¿Puedes enviarlo nuevamente?",
                )
                return {"status": "audio_download_error"}

            if transcription:
                text = transcription
                print("📝 Transcripción obtenida:", text)
            else:
                await send_text(
                    from_id,
                    "No pude transcribir tu audio. ¿Podrías intentarlo con otro mensaje?",
                )
                return {"status": "transcription_failed"}
        else:
            await send_text(
                from_id,
                "Por ahora solo puedo ayudarte con mensajes de texto o audios. 😊",
            )
            return {"status": "unsupported_type"}

        if not text:
            await send_text(
                from_id,
                "No recibí contenido para procesar. ¿Podrías enviarlo de nuevo?",
            )
            return {"status": "empty_text"}

        # ====================================================
        # 5) DETECTAR IDIOMA
        # ====================================================
        language = await detectar_idioma(text)
        print(f"🌍 Idioma detectado: {language}")

        # ====================================================
        # 5.b) EVALUAR SI HAY ERRORES QUE MEREZCAN CORRECCIÓN
        # ====================================================
        has_errors, severity = await evaluar_errores(text, language)
        print(f"🧐 ¿Tiene errores?: {has_errors}, severidad: {severity}")

        # ====================================================
        # 6) ELEGIR PROMPT EN FUNCIÓN DE SI HAY ERRORES
        # ====================================================
        if has_errors:
            system_prompt = PROMPT_CON_ERROR.format(language=language)
        else:
            system_prompt = PROMPT_SIN_ERROR.format(language=language)

        # ====================================================
        # 7) LLAMADA PRINCIPAL A OPENAI PARA GENERAR RESPUESTA
        # ====================================================
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.5,
        )

        reply_raw = completion.choices[0].message.content
        reply = reply_raw.strip() if reply_raw else "Lo siento, hubo un problema generando la respuesta."

        # ====================================================
        # 8) RESPONDER AL USUARIO POR WHATSAPP
        # ====================================================
        await send_text(from_id, reply)

        return {"status": "ok"}

    except Exception as e:
        print("❌ Error procesando webhook:", e)
        return {"status": "error", "detail": str(e)}


@app.get("/")
async def root():
    return {"status": "ok"}
