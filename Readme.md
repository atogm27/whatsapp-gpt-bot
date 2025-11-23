# 🤖 WhatsApp Multi-Bot (Idiomas + Chef)

Este proyecto es un backend en **FastAPI** conectado a **WhatsApp Cloud API** y **OpenAI** que permite tener **varios asistentes en un mismo número de WhatsApp**, con selección de modo mediante comandos:

- 🧠 Bot de idiomas (corrección + conversación)
- 🍳 Asistente chef

Cada usuario puede cambiar de modo escribiendo comandos en el propio chat de WhatsApp.

---

## ✅ ¿Cómo se usa desde WhatsApp?

En el chat con tu número de WhatsApp Business:

- ` /menu`  o `menu`  
  Muestra las opciones disponibles.

- ` /idiomas`  
  Cambia al **bot de idiomas**.  
  A partir de aquí, todos los mensajes (texto o audio) pasan por el pipeline:
  1. Detectar idioma
  2. Evaluar si hay errores
  3. Elegir prompt (corrección + explicación, o solo conversación)
  4. Responder usando OpenAI

- ` /chef`  
  Cambia al **asistente chef**.  
  Todos los mensajes se envían a la función `asistente_cheff` de `funciones_openai.py`.

> El modo se guarda por número de WhatsApp (`from_id`), así que cada usuario puede estar en un modo distinto.

---

## 🧱 Arquitectura general

1. **WhatsApp Cloud API**
   - Envía los mensajes entrantes al endpoint `/webhook` (POST).
   - El backend responde a través del endpoint de envío de mensajes de Meta.

2. **Backend FastAPI**
   - Endpoint `GET /webhook`: verificación del webhook con Meta.
   - Endpoint `POST /webhook`: recibe mensajes de WhatsApp, procesa y responde.
   - Soporta:
     - Mensajes de texto
     - Audios (descarga, transcribe con OpenAI y procesa como texto)

3. **OpenAI**
   - `OPENAI_MODEL` para:
     - Detección de idioma (via tools/function calling).
     - Evaluación de errores.
     - Respuesta del bot de idiomas (corrección + explicación o conversación natural).
   - `OPENAI_TRANSCRIBE_MODEL` para transcribir audios.

4. **Lógica de modos**
   - Constantes:
     ```python
     MODO_IDIOMAS = "idiomas"
     MODO_CHEF = "chef"
     ```
   - Diccionario en memoria:
     ```python
     user_sessions: dict[str, str] = {}
     ```
     donde `user_sessions[from_id] = modo_actual`.

---

## 📂 Archivos importantes

- `main.py` (o el nombre que le hayas puesto): contiene:
  - Configuración de FastAPI.
  - Config de WhatsApp Cloud API y OpenAI.
  - Webhook `/webhook`.
  - Lógica de modos y comandos.
  - Funciones auxiliares:
    - `send_text`
    - `download_media`
    - `transcribir_audio`
    - `detectar_idioma`
    - `evaluar_errores`
    - `generar_respuesta_idiomas`
    - `handle_command`

- `funciones_openai.py`:
  - Debe definir al menos:
    ```python
    def asistente_cheff(message: str) -> str:
        """
        Recibe el mensaje del usuario y devuelve la respuesta del asistente chef.
        Internamente puede usar OpenAI u otro modelo.
        """
        ...
        return respuesta_str
    ```

---

## 🔐 Variables de entorno

El backend usa las siguientes variables:

- `VERIFY_TOKEN`  
  Token de verificación del webhook (debe coincidir con el que configures en Meta).

- `WA_PHONE_ID`  
  `phone_number_id` de tu número de WhatsApp Business (lo da Meta).

- `WA_TOKEN`  
  Access Token de la API de WhatsApp Cloud.

- `OPENAI_API_KEY`  
  API Key de OpenAI.

- `OPENAI_MODEL` (opcional, por defecto `gpt-4o-mini`)  
  Modelo de chat principal.

- `OPENAI_TRANSCRIBE_MODEL` (opcional, por defecto `gpt-4o-mini-transcribe`)  
  Modelo para transcripción de audio.

Ejemplo (Linux/macOS):

```bash
export VERIFY_TOKEN="mi_verify_token"
export WA_PHONE_ID="123456789012345"
export WA_TOKEN="EAAXXX..."
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
export OPENAI_TRANSCRIBE_MODEL="gpt-4o-mini-transcribe"
