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


# ====== WEBHOOK VERIFICATION ======
@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge", ""))
    return PlainTextResponse("error: invalid token", status_code=403)


# ====== HELPER: SEND MESSAGE ======
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


# ====== HELPER: DETECT LANGUAGE ======
async def detectar_idioma(text: str):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "clasificar_mensaje",
                "description": "Detecta el idioma predominante del mensaje.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "description": "Idioma detectado (ej: español, inglés, alemán, francés, italiano, japonés, etc.)"
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
                    "Tu tarea consiste ÚNICAMENTE en detectar el idioma del mensaje "
                    "del usuario y devolverlo mediante la función 'clasificar_mensaje'. "
                    "No des texto adicional."
                )
            },
            {"role": "user", "content": text},
        ],
        tools=tools,
        tool_choice="auto",
    )

    tool_call = res.choices[0].message.tool_calls[0]
    args = json.loads(tool_call["function"]["arguments"])
    return args["language"]


# ====== MAIN WHATSAPP WEBHOOK (POST) ======
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

        text_obj = msg.get("text")
        text = text_obj.get("body").strip() if text_obj and text_obj.get("body") else None

        if not text:
            await send_text(from_id, "De momento solo puedo procesar mensajes de texto. 😊")
            return {"status": "no_text"}

        # ===== Detectar idioma del usuario =====
        language = await detectar_idioma(text)
        print(f"🌍 Idioma detectado: {language}")

        # ===== Crear prompt dinámico =====
        system_prompt = f"""
Eres un tutor experto del idioma {language}.
Debes responder SIEMPRE en {language}.
Corrige suavemente los errores del usuario.
Luego explica las correcciones brevemente en español.
Después ofrece una frase corta en {language} para practicar.
Sé amable, claro y paciente.

Ejemplo de formato:
1) Corrección en {language}
2) Explicación en español
3) Frase de práctica en {language}
"""

        # ===== Llamada principal a OpenAI =====
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.5,
        )

        reply = completion.choices[0].message.content.strip()

        # ===== Enviar al usuario =====
        await send_text(from_id, reply)

        return {"status": "ok"}

    except Exception as e:
        print("❌ Error procesando webhook:", e)
        return {"status": "error", "detail": str(e)}
