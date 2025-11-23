import io
import os
import json
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import httpx
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageToolCall,
    ChatCompletionToolParam,
)

from funciones_openai import asistente_cheff  # versión moderna async (Responses API)

# ====================================================
# 0) CONSTANTES DE PROMPTS (BOT DE IDIOMAS)
# ====================================================

PROMPT_CON_ERROR = """
Eres un tutor experto del idioma {language}.
Debes responder siempre en {language}.

1) Corrige suavemente el texto (gramática, vocabulario, estilo).
2) Explica en español los errores más importantes y la regla básica.
3) Responde en {language} para continuar la conversación.

Sé amable, motivador y breve.
"""

PROMPT_SIN_ERROR = """
Eres un hablante del idioma {language}.
Responde de forma natural en {language}, como en una conversación.
No señales errores a menos que el usuario lo pida.
Sé amable y fomenta que el usuario siga practicando.
"""

# ====================================================
# 0.b) DEFINICIÓN DE TOOLS PARA CHAT COMPLETIONS
# ====================================================

LANGUAGE_TOOL: ChatCompletionToolParam = {
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

ERRORS_TOOL: ChatCompletionToolParam = {
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
# MODOS Y SESIONES
# ====================================================

MODO_IDIOMAS = "idiomas"
MODO_CHEF = "chef"

user_sessions: dict[str, str] = {}

# ====================================================
# APP + CONFIG
# ====================================================

app = FastAPI()

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "")
WA_TOKEN = os.environ.get("WA_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

OPENAI_MODEL_TEXT = os.environ.get("OPENAI_MODEL_TEXT", "gpt-4o-mini")
OPENAI_MODEL_TRANSCRIBE = os.environ.get("OPENAI_MODEL_TRANSCRIBE", "gpt-4o-mini-transcribe")

if not VERIFY_TOKEN:
    print("⚠️ Falta VERIFY_TOKEN")
if not WA_PHONE_ID:
    print("⚠️ Falta WA_PHONE_ID")
if not WA_TOKEN:
    print("⚠️ Falta WA_TOKEN")
if not OPENAI_API_KEY:
    print("⚠️ Falta OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
GRAPH_URL = f"https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages"

# ====================================================
# 1) VERIFY WEBHOOK
# ====================================================

@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge", ""))
    return PlainTextResponse("error: invalid token", status_code=403)

# ====================================================
# 2) SEND TEXT
# ====================================================

async def send_text(to: str, body: str):
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

    async with httpx.AsyncClient(timeout=30) as httpc:
        r = await httpc.post(GRAPH_URL, json=payload, headers=headers)
        print("📤 WA Res:", r.status_code, r.text)

# ====================================================
# 2.b) DOWNLOAD MEDIA
# ====================================================

async def download_media(media_id: str):
    headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    base = "https://graph.facebook.com/v20.0"

    async with httpx.AsyncClient(timeout=30) as httpc:
        meta = await httpc.get(f"{base}/{media_id}", headers=headers)
        meta.raise_for_status()
        info = meta.json()

        url = info["url"]
        mime = info.get("mime_type", "")

        audio_res = await httpc.get(url, headers=headers)
        audio_res.raise_for_status()

        return audio_res.content, mime

# ====================================================
# 2.c) TRANSCRIBE
# ====================================================

def _ext_from_mime(mime: str):
    if "wav" in mime:
        return "wav"
    if "ogg" in mime:
        return "ogg"
    if "m4a" in mime:
        return "m4a"
    return "mp3"

async def transcribir_audio(audio_bytes: bytes, mime_type: str | None):
    ext = _ext_from_mime(mime_type or "")
    f = io.BytesIO(audio_bytes)
    f.name = f"audio.{ext}"

    try:
        res = await client.audio.transcriptions.create(
            model=OPENAI_MODEL_TRANSCRIBE,
            file=f,
            response_format="text"
        )
        return res.strip()
    except Exception as e:
        print("❌ Error transcribiendo:", e)
        return None

# ====================================================
# X) DETECTAR IDIOMA – usando Chat Completions + tools
# ====================================================

async def detectar_idioma(text: str) -> str:
    res = await client.chat.completions.create(
        model=OPENAI_MODEL_TEXT,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu única tarea es detectar el idioma del texto del usuario "
                    "y devolverlo mediante la función 'clasificar_mensaje'. "
                    "No añadas texto adicional."
                ),
            },
            {"role": "user", "content": text},
        ],
        tools=[LANGUAGE_TOOL],
        tool_choice="auto",
    )

    msg = res.choices[0].message
    tool_calls = msg.tool_calls or []
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al detectar idioma:", res)
        return "desconocido"

    tool_call = cast(ChatCompletionMessageToolCall, tool_calls[0])
    args_json = tool_call.function.arguments
    args = json.loads(args_json)

    language = args.get("language", "desconocido")
    return language

# ====================================================
# X.b) DETECTAR ERRORES – usando Chat Completions + tools
# ====================================================

async def evaluar_errores(text: str, language: str):
    """
    Devuelve:
      has_errors: bool -> True si merece la pena corregir, False si el texto está bien.
      severity: str    -> 'ninguno', 'leve', 'moderado', 'alto'
    """
    res = await client.chat.completions.create(
        model=OPENAI_MODEL_TEXT,
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

    msg = res.choices[0].message
    tool_calls = msg.tool_calls or []
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al evaluar errores:", res)
        return False, "ninguno"

    tool_call = cast(ChatCompletionMessageToolCall, tool_calls[0])
    args_json = tool_call.function.arguments
    args = json.loads(args_json)

    has_errors = bool(args.get("has_errors", False))
    severity = args.get("severity", "ninguno")

    return has_errors, severity

# ====================================================
# BOT IDIOMAS – usando Chat Completions
# ====================================================

async def generar_respuesta_idiomas(text: str):
    language = await detectar_idioma(text)
    print(f"🌍 Idioma detectado: {language}")

    has_errors, severity = await evaluar_errores(text, language)
    print(f"🧐 ¿Tiene errores?: {has_errors}, severidad: {severity}")

    system_prompt = (
        PROMPT_CON_ERROR if has_errors else PROMPT_SIN_ERROR
    ).format(language=language)

    completion = await client.chat.completions.create(
        model=OPENAI_MODEL_TEXT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.5,
    )

    reply_raw = completion.choices[0].message.content
    reply = reply_raw.strip() if reply_raw else "Lo siento, hubo un problema generando la respuesta."
    return reply

# ====================================================
# COMANDOS
# ====================================================

def handle_command(uid: str, text: str):
    t = text.strip().lower()

    if t in ("/menu", "menu"):
        return (
            "🧠 *Menú de asistentes*\n"
            "- /idiomas → Bot de idiomas\n"
            "- /chef → Asistente chef 🍳"
        )

    if t == "/idiomas":
        user_sessions[uid] = MODO_IDIOMAS
        return "Modo cambiado a 🧠 *Idiomas*"

    if t == "/chef":
        user_sessions[uid] = MODO_CHEF
        return "Modo cambiado a 🍳 *Chef*"

    return "Comando no reconocido. Usa /menu"

# ====================================================
# WEBHOOK
# ====================================================

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        messages = value.get("messages", [])

        if not messages:
            return {"status": "no_messages"}

        msg = messages[0]
        uid = msg["from"]

        # ========================
        # TEXTO O AUDIO
        # ========================
        msg_type = msg.get("type")

        if msg_type == "text":
            text = msg["text"]["body"].strip()

        elif msg_type in ("audio", "voice"):
            media_id = msg[msg_type]["id"]
            audio_bytes, mime = await download_media(media_id)
            text = await transcribir_audio(audio_bytes, mime)
        else:
            await send_text(uid, "Solo acepto texto o audio 🙂")
            return {"status": "unsupported"}

        if not text:
            await send_text(uid, "No pude leer tu mensaje.")
            return {"status": "empty"}

        # ========================
        # COMANDOS
        # ========================
        if text.startswith("/"):
            reply = handle_command(uid, text)
            await send_text(uid, reply)
            return {"status": "command"}

        # ========================
        # MODO
        # ========================
        mode = user_sessions.get(uid, MODO_IDIOMAS)

        if mode == MODO_CHEF:
            print("🍳 Modo actual: CHEF")
            reply = await asistente_cheff(text)   # usa Responses API en funciones_openai.py
        else:
            print("🧠 Modo actual: IDIOMAS")
            reply = await generar_respuesta_idiomas(text)

        await send_text(uid, reply)
        return {"status": "ok"}

    except Exception as e:
        print("❌ ERROR:", e)
        return {"error": str(e)}

# ====================================================
# ROOT
# ====================================================

@app.get("/")
async def root():
    return {"status": "ok"}
