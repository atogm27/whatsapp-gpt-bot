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


# ====== 1) VERIFICACIÓN DEL WEBHOOK (GET) ======
@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("error: invalid token", status_code=403)


# ====== 2) RECEPCIÓN DE MENSAJES (POST) ======
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
        from_id = msg["from"]  # número del usuario

        # ===== Obtener el texto de forma segura =====
        text_obj = msg.get("text")
        text = text_obj.get("body").strip() if text_obj and text_obj.get("body") else None

        if not text:
            await send_text(from_id, "De momento solo puedo procesar mensajes de texto. 😊")
            return {"status": "no_text"}

        # ===== Llamada a OpenAI =====
        system_prompt = (
             "Eres un tutor de idiomas especializado en inglés y alemán. "
    "Debes responder SIEMPRE en el mismo idioma en el que te escriba el usuario. "

    "Tu tarea es: "
    "1) Corregir suavemente cualquier error (gramatical, léxico, ortográfico o de estilo). "
    "2) Explicar brevemente la corrección SIEMPRE en español, incluyendo la regla gramatical relevante "
    "   cuando sea útil (por ejemplo: uso de tiempos verbales, preposiciones, orden de palabras, casos, artículos, etc.). "
    "3) Ofrecer una frase o pregunta corta en el mismo idioma del mensaje original para practicar. "

    "Usa un tono amable, claro y paciente. "
    
    "EJEMPLOS DE COMPORTAMIENTO:\n"
    "- Si el usuario escribe en inglés: 'Yesterday I go to the park with my friend.'\n"
    "  → Responder en inglés con la frase corregida: 'Yesterday I went to the park with my friend.'\n"
    "  → Luego explicar en español: 'Se usa el pasado simple 'went' en lugar de 'go' porque la acción ocurrió ayer.'\n"
    "  → Ofrecer una frase de práctica en inglés: 'Where did you go last weekend?'\n\n"

    "- Si el usuario escribe en alemán: 'Ich habe gestern ins Kino gehen.'\n"
    "  → Responder en alemán con la frase corregida: 'Ich bin gestern ins Kino gegangen.'\n"
    "  → Explicar en español: 'Con verbos de movimiento se usa normalmente el auxiliar 'sein' en el Perfekt. "
    "Además, el participio de 'gehen' es 'gegangen'.'\n"
    "  → Frase de práctica en alemán: 'Wohin bist du letztes Wochenende gefahren?'"
        )

        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.5,
        )

        reply_raw = completion.choices[0].message.content

        if not reply_raw:
            print("❌ OpenAI devolvió un mensaje vacío:", completion)
            reply = "Lo siento, hubo un problema generando la respuesta. ¿Puedes repetir el mensaje?"
        else:
            reply = reply_raw.strip()


        # ===== Responder al usuario por WhatsApp =====
        await send_text(from_id, reply)

        return {"status": "ok"}

    except Exception as e:
        print("❌ Error procesando webhook:", e)
        return {"status": "error", "detail": str(e)}


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
