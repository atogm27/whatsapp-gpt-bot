# funciones_openai.py
from openai import AsyncOpenAI

# Debes inicializar el cliente DENTRO del archivo o pasarlo desde fuera.
# Vamos a usar la opción de CREARLO AQUÍ dentro (sencillo y claro).
client = AsyncOpenAI()

async def asistente_cheff(message: str) -> str:
    """
    Asistente culinario usando la nueva API 'responses.create'
    y en versión async.
    """

    response = await client.responses.create(
        model="gpt-4o-mini",   # o GPT-4.1, GPT-4o, etc.
        input=[
            {
                "role": "system",
                "content": """Eres un asistente culinario especializado en mejorar platos.
Cuando el usuario describa un plato, un problema o pida sugerencias:

No harás preguntas de aclaración.
Siempre devolverás una única respuesta completa.
Incluirás razonamiento breve antes de cada recomendación.
Ofrecerás mejoras prácticas y aplicables.
Tono amable, alentador y creativo.
Respuestas en párrafos breves o listas con viñetas.

🔧 FORMATO:
- Razonamiento breve inicial
- Sugerencias específicas (cada una con su razonamiento interno)
"""
            },
            {
                "role": "user",
                "content": message
            }
        ]
    )

    # La API moderna siempre expone la salida como:
    # response.output_text
    return response.output_text.strip()
