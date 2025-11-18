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
async def detectar_idioma(text: str):
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
                    "required": ["language"]
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
                    "y devolverlo mediante la función 'clasificar_mensaje'."
                ),
            },
            {"role": "user", "content": text},
        ],
        tools=tools,
        tool_choice="auto",
    )

    # === CORREGIDO: ACCESO A LOS ARGUMENTOS DEL TOOL_CALL ===
    tool_calls = res.choices[0].message.tool_calls
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls:", res)
        return "desconocido"

    tool_call = tool_calls[0]
    args_json = tool_call.function.arguments
    args = json.loads(args_json)

    language = args.get("language", "desconocido")
    return language


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
        # 5) DETECTAR IDIOMA DE FORMA AUTOMÁTICA
        # ====================================================
        language = await detectar_idioma(text)
        print(f"🌍 Idioma detectado: {language}")

        # ====================================================
        # 6) PROMPT DINÁMICO BASADO EN EL IDIOMA DETECTADO
        # ====================================================
        system_prompt = f"""
Eres un tutor experto del idioma {language}.
Debes responder siempre en {language}.
Corrige suavemente los errores del usuario.
Después explica la corrección en español.
Luego ofrece una frase corta en {language} para practicar.

Formato de respuesta:
1) Corrección en {language}
2) Explicación en español
3) Frase de práctica en {language}
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

        reply = completion.choices[0].message.content.strip()

        # ====================================================
        # 8) RESPONDER AL USUARIO POR WHATSAPP
        # ====================================================
        await send_text(from_id, reply)

        return {"status": "ok"}

    except Exception as e:
        print("❌ Error procesando webhook:", e)
        return {"status": "error", "detail": str(e)}
