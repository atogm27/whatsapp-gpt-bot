import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import httpx
from openai import OpenAI

app = FastAPI()

# ====== VARIABLES DE ENTORNO ======
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "")
WA_TOKEN = os.environ.get("WA_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

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
# 3) FUNCIÓN PARA DETECTAR EL IDIOMA DEL MENSAJE
# ====================================================
async def detectar_idioma(text: str) -> str:
    tools = [
        {
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
                            )
                        }
                    },
                    "required": ["language"],
                },
            },
        }
    ]

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
        tools=tools,
        tool_choice="auto",
    )

    tool_calls = res.choices[0].message.tool_calls
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al detectar idioma:", res)
        return "desconocido"

    tool_call = tool_calls[0]
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
    tools = [
        {
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
    ]

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
        tools=tools,
        tool_choice="auto",
        temperature=0,
    )

    tool_calls = res.choices[0].message.tool_calls
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al evaluar errores:", res)
        return False, "ninguno"

    tool_call = tool_calls[0]
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

        # === obtener el texto ===
        text_obj = msg.get("text")
        text = (
            text_obj.get("body").strip()
            if text_obj and text_obj.get("body")
            else None
        )

        if not text:
            await send_text(from_id, "De momento solo puedo procesar mensajes de texto. 😊")
            return {"status": "no_text"}

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
            # MODO: responde + corrige
            system_prompt = f"""
Eres un tutor experto del idioma {language}.
Debes responder siempre en {language}.

1) Corrige suavemente el texto del usuario (gramática, vocabulario, estilo).
2) Explica brevemente en español los errores más importantes y la regla básica. Que quede claro el error que hay que corregir.

3) Responder en {language} de forma natural, como en una conversación para seguir la conversación del alumno.


No seas excesivamente extenso. Sé amable, motivador y fomenta que el usuario siga practicando.Intenta que la conversación sea agradable y amena. Interesate por cualquier gusto que parezca tener.
"""
        else:
            # MODO: solo responde (sin corregir)
            system_prompt = f"""
Eres un habalnte del idioma {language}.

Tu tarea es:
Responder en {language} de forma natural, como en una conversación para seguir la conversación del alumno.

No reescribas el texto del usuario ni señales errores,
   salvo que él lo pida explícitamente.

Sé amable, motivador y fomenta que el usuario siga practicando.Intenta que la conversación sea agradable y amena. Interesate por cualquier gusto que parezca tener.
"""

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
