"""
=============================================================
🧠 SISTEMA DE MEMORIA - Para el Agente Pro
=============================================================

Este módulo agrega memoria persistente al agente:

1. Memoria de conversaciones: guarda el historial completo
2. Memoria de hechos: recuerda datos clave del usuario
   (nombre, preferencias, tareas frecuentes, etc.)

Los datos se guardan en archivos JSON que persisten
entre sesiones. El agente recuerda todo incluso después
de reiniciarlo.

=============================================================
"""

import json
import os
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic


# =============================================================
# CONFIGURACIÓN
# =============================================================

MEMORIA_DIR = Path("memoria")
MEMORIA_DIR.mkdir(exist_ok=True)

ARCHIVO_HECHOS = MEMORIA_DIR / "hechos.json"
ARCHIVO_CONVERSACIONES = MEMORIA_DIR / "conversaciones.json"
ARCHIVO_RESUMEN = MEMORIA_DIR / "resumen_contexto.json"

MAX_MENSAJES_CONTEXTO = 20  # Mensajes recientes a enviar a Claude
MAX_CONVERSACIONES_GUARDADAS = 100  # Máximo de intercambios guardados


# =============================================================
# MEMORIA DE HECHOS (datos clave del usuario)
# =============================================================

def cargar_hechos() -> dict:
    """Carga los hechos recordados del usuario."""
    if ARCHIVO_HECHOS.exists():
        try:
            with open(ARCHIVO_HECHOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"hechos": [], "actualizado": ""}
    return {"hechos": [], "actualizado": ""}


def guardar_hechos(datos: dict):
    """Guarda los hechos del usuario."""
    datos["actualizado"] = datetime.now().isoformat()
    with open(ARCHIVO_HECHOS, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def agregar_hecho(hecho: str) -> str:
    """Agrega un hecho nuevo a la memoria."""
    datos = cargar_hechos()

    # Evitar duplicados
    for h in datos["hechos"]:
        if h["contenido"].lower().strip() == hecho.lower().strip():
            return f"Ya recuerdo eso: '{hecho}'"

    datos["hechos"].append({
        "contenido": hecho,
        "fecha": datetime.now().isoformat(),
    })
    guardar_hechos(datos)
    return f"Guardado en memoria: '{hecho}'"


def eliminar_hecho(indice: int) -> str:
    """Elimina un hecho por su índice (empezando en 1)."""
    datos = cargar_hechos()
    idx = indice - 1
    if 0 <= idx < len(datos["hechos"]):
        eliminado = datos["hechos"].pop(idx)
        guardar_hechos(datos)
        return f"Olvidado: '{eliminado['contenido']}'"
    return f"Índice {indice} no válido. Tengo {len(datos['hechos'])} hechos guardados."


def listar_hechos() -> str:
    """Lista todos los hechos recordados."""
    datos = cargar_hechos()
    if not datos["hechos"]:
        return "No tengo nada guardado en memoria todavía."

    texto = f"Tengo {len(datos['hechos'])} cosas en memoria:\n\n"
    for i, h in enumerate(datos["hechos"], 1):
        fecha = h["fecha"][:10]
        texto += f"{i}. {h['contenido']} (guardado: {fecha})\n"

    return texto


def obtener_contexto_hechos() -> str:
    """Genera un texto con todos los hechos para incluir en el prompt."""
    datos = cargar_hechos()
    if not datos["hechos"]:
        return ""

    texto = "MEMORIA DEL USUARIO (datos que recuerdas de conversaciones anteriores):\n"
    for h in datos["hechos"]:
        texto += f"- {h['contenido']}\n"

    return texto


# =============================================================
# MEMORIA DE CONVERSACIONES
# =============================================================

def cargar_conversaciones() -> list:
    """Carga el historial de conversaciones."""
    if ARCHIVO_CONVERSACIONES.exists():
        try:
            with open(ARCHIVO_CONVERSACIONES, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def guardar_conversaciones(conversaciones: list):
    """Guarda el historial de conversaciones."""
    # Limitar el tamaño
    if len(conversaciones) > MAX_CONVERSACIONES_GUARDADAS:
        conversaciones = conversaciones[-MAX_CONVERSACIONES_GUARDADAS:]

    with open(ARCHIVO_CONVERSACIONES, "w", encoding="utf-8") as f:
        json.dump(conversaciones, f, ensure_ascii=False, indent=2)


def agregar_intercambio(pregunta: str, respuesta: str):
    """Guarda un intercambio (pregunta + respuesta) en el historial."""
    conversaciones = cargar_conversaciones()
    conversaciones.append({
        "fecha": datetime.now().isoformat(),
        "usuario": pregunta,
        "agente": respuesta[:500],  # Limitar tamaño de respuesta guardada
    })
    guardar_conversaciones(conversaciones)


def obtener_conversaciones_recientes(n: int = 5) -> str:
    """Obtiene las últimas N conversaciones como contexto."""
    conversaciones = cargar_conversaciones()
    if not conversaciones:
        return ""

    recientes = conversaciones[-n:]
    texto = "CONVERSACIONES RECIENTES (para contexto):\n"
    for c in recientes:
        fecha = c["fecha"][:10]
        texto += f"[{fecha}] Usuario: {c['usuario'][:100]}\n"
        texto += f"[{fecha}] Agente: {c['agente'][:200]}\n\n"

    return texto


# =============================================================
# RESUMEN AUTOMÁTICO DE CONTEXTO
# =============================================================

def generar_resumen_contexto(conversaciones_nuevas: list) -> str:
    """
    Usa Claude para generar un resumen del contexto acumulado.
    Se ejecuta periódicamente para mantener la memoria compacta.
    """
    if not conversaciones_nuevas:
        return ""

    try:
        client = Anthropic()

        # Cargar resumen anterior si existe
        resumen_anterior = ""
        if ARCHIVO_RESUMEN.exists():
            with open(ARCHIVO_RESUMEN, "r", encoding="utf-8") as f:
                data = json.load(f)
                resumen_anterior = data.get("resumen", "")

        texto_conversaciones = ""
        for c in conversaciones_nuevas:
            texto_conversaciones += f"Usuario: {c['usuario'][:150]}\nAgente: {c['agente'][:200]}\n\n"

        prompt = f"""Eres un sistema de memoria. Tu tarea es actualizar el resumen de lo que sabes del usuario.

RESUMEN ANTERIOR:
{resumen_anterior if resumen_anterior else "(vacío - primera vez)"}

NUEVAS CONVERSACIONES:
{texto_conversaciones}

INSTRUCCIONES:
1. Combina el resumen anterior con la información nueva
2. Extrae datos clave: nombre, preferencias, proyectos, temas de interés
3. Mantén el resumen corto (máximo 300 palabras)
4. Formato: lista de hechos importantes sobre el usuario
5. Devuelve SOLO el resumen actualizado, sin explicaciones"""

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        resumen = "".join(b.text for b in resp.content if hasattr(b, "text"))

        # Guardar resumen
        with open(ARCHIVO_RESUMEN, "w", encoding="utf-8") as f:
            json.dump({
                "resumen": resumen,
                "actualizado": datetime.now().isoformat(),
                "n_conversaciones_procesadas": len(conversaciones_nuevas)
            }, f, ensure_ascii=False, indent=2)

        return resumen

    except Exception as e:
        return f"Error generando resumen: {str(e)}"


def obtener_resumen() -> str:
    """Obtiene el resumen de contexto actual."""
    if ARCHIVO_RESUMEN.exists():
        try:
            with open(ARCHIVO_RESUMEN, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("resumen", "")
        except Exception:
            return ""
    return ""


# =============================================================
# HERRAMIENTAS DE MEMORIA PARA CLAUDE
# =============================================================

HERRAMIENTAS_MEMORIA = [
    {
        "name": "recordar_hecho",
        "description": (
            "Guarda un dato importante sobre el usuario en la memoria a largo plazo. "
            "Usa esta herramienta cuando el usuario comparta información personal relevante "
            "como su nombre, trabajo, preferencias, proyectos, fechas importantes, etc. "
            "También úsala cuando el usuario diga explícitamente 'recuerda que...' o 'acuérdate de...'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hecho": {
                    "type": "string",
                    "description": "El dato a recordar (ej: 'El usuario se llama Oswaldo', 'Trabaja en desarrollo de software')"
                }
            },
            "required": ["hecho"]
        }
    },
    {
        "name": "olvidar_hecho",
        "description": (
            "Elimina un dato de la memoria. Usa cuando el usuario diga 'olvida que...', "
            "'ya no es cierto que...', o pida borrar algo de la memoria."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "indice": {
                    "type": "integer",
                    "description": "Número del hecho a olvidar (usa listar_memoria primero para ver los números)"
                }
            },
            "required": ["indice"]
        }
    },
    {
        "name": "listar_memoria",
        "description": (
            "Muestra todo lo que el agente recuerda del usuario. "
            "Usa cuando pregunten '¿qué recuerdas de mí?', '¿qué sabes de mí?', "
            "'muéstrame tu memoria', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

FUNCIONES_MEMORIA = {
    "recordar_hecho": lambda a: agregar_hecho(a["hecho"]),
    "olvidar_hecho": lambda a: eliminar_hecho(a["indice"]),
    "listar_memoria": lambda a: listar_hechos(),
}


def obtener_system_prompt_con_memoria(system_prompt_base: str) -> str:
    """
    Enriquece el system prompt con la memoria del usuario.
    Se usa antes de cada llamada a Claude.
    """
    contexto_hechos = obtener_contexto_hechos()
    resumen = obtener_resumen()
    conversaciones = obtener_conversaciones_recientes(5)

    memoria_texto = ""

    if contexto_hechos:
        memoria_texto += f"\n\n{contexto_hechos}"

    if resumen:
        memoria_texto += f"\nRESUMEN DE INTERACCIONES ANTERIORES:\n{resumen}\n"

    if conversaciones:
        memoria_texto += f"\n{conversaciones}"

    if memoria_texto:
        memoria_texto = (
            "\n\n## MEMORIA A LARGO PLAZO\n"
            "Tienes acceso a memoria persistente. Usa esta información para personalizar "
            "tus respuestas y recordar el contexto del usuario. "
            "Cuando el usuario comparta datos importantes, usa la herramienta 'recordar_hecho' "
            "para guardarlos. Nunca menciones la mecánica interna de tu memoria.\n"
            + memoria_texto
        )

    return system_prompt_base + memoria_texto


# =============================================================
# ACTUALIZACIÓN PERIÓDICA DEL RESUMEN
# =============================================================

_contador_mensajes = 0

def verificar_actualizacion_resumen():
    """
    Verifica si es momento de actualizar el resumen.
    Se ejecuta cada 10 mensajes.
    """
    global _contador_mensajes
    _contador_mensajes += 1

    if _contador_mensajes >= 10:
        _contador_mensajes = 0
        conversaciones = cargar_conversaciones()
        if conversaciones:
            ultimas = conversaciones[-10:]
            generar_resumen_contexto(ultimas)
