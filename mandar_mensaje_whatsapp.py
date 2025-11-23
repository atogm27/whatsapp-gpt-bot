


# def send_whatsapp_template(template_name: str, nombre_destinatario: str, cuerpo_ia: str):
#     """
#     Enviar mensaje usando una PLANTILLA aprobada.
#     - template_name: nombre de la plantilla en WhatsApp Manager (ej: 'daily_ai_digest')
#     - nombre_destinatario: valor para {{1}}
#     - cuerpo_ia: valor para {{2}} (el texto generado por la IA)
#     """
#     url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

#     headers = {
#         "Authorization": f"Bearer {WHATSAPP_TOKEN}",
#         "Content-Type": "application/json"
#     }

#     data = {
#         "messaging_product": "whatsapp",
#         "to": MY_PERSONAL_NUMBER,
#         "type": "template",
#         "template": {
#             "name": template_name,
#             "language": {
#                 "code": "es_ES"  # o el código que tenga tu plantilla
#             },
#             "components": [
#                 {
#                     "type": "body",
#                     "parameters": [
#                         { "type": "text", "text": nombre_destinatario },  # {{1}}
#                         { "type": "text", "text": cuerpo_ia }            # {{2}}
#                     ]
#                 }
#             ]
#         }
#     }

#     response = requests.post(url, headers=headers, json=data)
#     print("TEMPLATE:", response.status_code, response.text)
