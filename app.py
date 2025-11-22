import json

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from message_processing import MessageProcessingError, resolve_message_text
from messaging import extract_incoming_message
from openai_functions import detectar_idioma, evaluar_errores
from prompts import PROMPT_CON_ERROR, PROMPT_SIN_ERROR
from settings import OPENAI_MODEL, VERIFY_TOKEN, client
from whatsapp import send_text

app = FastAPI()


@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")

    return PlainTextResponse("error: invalid token", status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    print("📩 Webhook recibido:", json.dumps(data, indent=2, ensure_ascii=False))

    try:
        message = extract_incoming_message(data)
        if not message:
            return {"status": "no_messages"}

        from_id = message.sender

        try:
            text = await resolve_message_text(message)
        except MessageProcessingError as exc:
            if from_id:
                await send_text(from_id, exc.user_message)
            else:
                print("⚠️ No se pudo enviar respuesta al usuario:", exc.user_message)
            return {"status": exc.status}

        language = await detectar_idioma(text)
        print(f"🌍 Idioma detectado: {language}")

        has_errors, severity = await evaluar_errores(text, language)
        print(f"🧐 ¿Tiene errores?: {has_errors}, severidad: {severity}")

        if has_errors:
            system_prompt = PROMPT_CON_ERROR.format(language=language)
        else:
            system_prompt = PROMPT_SIN_ERROR.format(language=language)

        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.5,
        )

        reply_raw = completion.choices[0].message.content
        reply = (
            reply_raw.strip()
            if reply_raw
            else "Lo siento, hubo un problema generando la respuesta."
        )

        await send_text(from_id, reply)

        return {"status": "ok"}

    except Exception as e:
        print("❌ Error procesando webhook:", e)
        return {"status": "error", "detail": str(e)}


@app.get("/")
async def root():
    return {"status": "ok"}
