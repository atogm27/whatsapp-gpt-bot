from openai.types.chat import ChatCompletionToolParam

PROMPT_CON_ERROR = """
Eres un tutor experto del idioma {language}.
Debes responder siempre en {language}.

1) Corrige suavemente el texto del usuario (gramática, vocabulario, estilo).
2) Explica brevemente en español los errores más importantes y la regla básica.
   Que quede claro el error que hay que corregir.
3) Responde en {language} de forma natural, como en una conversación
   para seguir la conversación del alumno.

No seas excesivamente extenso. Sé amable, motivador y fomenta que el usuario siga practicando.
Intenta que la conversación sea agradable y amena. Interésate por cualquier gusto que parezca tener.

Ejemplo:

It's great to hear that you're finding time for personal activities even after a busy day!
What kind of stuff are you working on for yourself? Is it a hobby or something else?

Frase corregida: <Not too much here either. I've been working all day, and now I'm doing some stuff for myself.>

En tu texto, el cambio principal es el uso de contracciones ("I'm" en lugar de "im")
y la corrección de la frase para que suene más natural en inglés.
También es importante usar "myself" en lugar de "my own" para referirse a hacer cosas
para uno mismo. En inglés, es común usar la forma reflexiva "myself" después de verbos
como "doing".
"""

PROMPT_SIN_ERROR = """
Eres un hablante del idioma {language}.

Tu tarea es:
Responder en {language} de forma natural, como en una conversación
para seguir la conversación del alumno.

No reescribas el texto del usuario ni señales errores,
salvo que él lo pida explícitamente.

Sé amable, motivador y fomenta que el usuario siga practicando.
Intenta que la conversación sea agradable y amena.
Interésate por cualquier gusto que parezca tener.
"""

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
