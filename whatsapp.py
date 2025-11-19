import httpx

from settings import GRAPH_URL, WA_TOKEN


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
