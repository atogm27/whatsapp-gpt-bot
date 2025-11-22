import json
from typing import cast

from openai.types.chat import ChatCompletionMessageToolCall

from prompts import ERRORS_TOOL, LANGUAGE_TOOL
from settings import OPENAI_MODEL, client


async def detectar_idioma(text: str) -> str:
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
        tools=[LANGUAGE_TOOL],
        tool_choice="auto",
    )

    tool_calls = res.choices[0].message.tool_calls or []
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al detectar idioma:", res)
        return "desconocido"

    tool_call = cast(ChatCompletionMessageToolCall, tool_calls[0])
    args_json = tool_call.function.arguments
    args = json.loads(args_json)

    language = args.get("language", "desconocido")
    return language


async def evaluar_errores(text: str, language: str):
    """
    Devuelve:
      has_errors: bool -> True si merece la pena corregir, False si el texto está bien.
      severity: str    -> 'ninguno', 'leve', 'moderado', 'alto'
    """

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
        tools=[ERRORS_TOOL],
        tool_choice="auto",
        temperature=0,
    )

    tool_calls = res.choices[0].message.tool_calls or []
    if not tool_calls:
        print("⚠️ No se devolvieron tool_calls al evaluar errores:", res)
        return False, "ninguno"

    tool_call = cast(ChatCompletionMessageToolCall, tool_calls[0])
    args_json = tool_call.function.arguments
    args = json.loads(args_json)

    has_errors = bool(args.get("has_errors", False))
    severity = args.get("severity", "ninguno")

    return has_errors, severity
