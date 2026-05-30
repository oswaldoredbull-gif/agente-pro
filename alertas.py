"""
=============================================================
🔔 SISTEMA DE ALERTAS - Recordatorios por Telegram
=============================================================

Envía recordatorios automáticos según la prioridad:
  🔴 Alta    = cada 2 horas
  🟡 Media   = cada 4 horas
  🟢 Baja    = día siguiente a las 8:00 AM

=============================================================
"""

import os
import time
import json
import threading
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Zona horaria de México
MEXICO_TZ = timezone(timedelta(hours=-6))

# Archivo para trackear alertas enviadas
ALERTAS_FILE = "alertas_enviadas.json"

# Configuración de intervalos (en horas)
INTERVALOS = {
    "alta": 2,
    "media": 4,
    "baja": None  # Se maneja diferente: solo a las 8 AM
}

HORA_ALERTA_BAJA = 8  # 8:00 AM para prioridad baja


def cargar_alertas_enviadas():
    """Carga el registro de alertas enviadas."""
    if Path(ALERTAS_FILE).exists():
        try:
            with open(ALERTAS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def guardar_alertas_enviadas(alertas):
    """Guarda el registro de alertas enviadas."""
    try:
        with open(ALERTAS_FILE, "w") as f:
            json.dump(alertas, f)
    except Exception:
        pass


def obtener_tareas_pendientes():
    """Obtiene tareas pendientes de Supabase o SQLite."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if supabase_url and supabase_key:
        try:
            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json"
            }
            r = requests.get(
                f"{supabase_url}/tareas?select=*&estado=eq.pendiente&order=id.asc",
                headers=headers, timeout=10
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"Error obteniendo tareas: {e}")
        return []
    else:
        # Fallback a SQLite local
        try:
            import sqlite3
            import platform
            if platform.system() == "Windows":
                db = r"C:\Users\omurillo\.gemini\antigravity\scratch\claude_agent\agente_datos.db"
            else:
                db = "agente_datos.db"
            conn = sqlite3.connect(db)
            c = conn.cursor()
            c.execute("SELECT id, titulo, descripcion, estado, prioridad, creado_en FROM tareas WHERE estado='pendiente'")
            cols = [d[0] for d in c.description]
            rows = c.fetchall()
            conn.close()
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []


def enviar_alerta_telegram(bot_token, chat_id, mensaje):
    """Envía un mensaje de alerta por Telegram."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": mensaje,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Error enviando alerta: {e}")
        return False


def formatear_alerta(tareas_por_prioridad):
    """Formatea el mensaje de alerta."""
    ahora = datetime.now(MEXICO_TZ)
    hora_str = ahora.strftime("%H:%M")

    mensaje = f"🔔 *RECORDATORIO DE TAREAS*\n"
    mensaje += f"📅 {hora_str} hrs\n"
    mensaje += "─────────────────\n\n"

    total = 0

    if tareas_por_prioridad.get("alta"):
        mensaje += "🔴 *PRIORIDAD ALTA* (cada 2 hrs)\n"
        for t in tareas_por_prioridad["alta"]:
            mensaje += f"  • {t['titulo']}\n"
            total += 1
        mensaje += "\n"

    if tareas_por_prioridad.get("media"):
        mensaje += "🟡 *PRIORIDAD MEDIA* (cada 4 hrs)\n"
        for t in tareas_por_prioridad["media"]:
            mensaje += f"  • {t['titulo']}\n"
            total += 1
        mensaje += "\n"

    if tareas_por_prioridad.get("baja"):
        mensaje += "🟢 *PRIORIDAD BAJA*\n"
        for t in tareas_por_prioridad["baja"]:
            mensaje += f"  • {t['titulo']}\n"
            total += 1
        mensaje += "\n"

    mensaje += f"─────────────────\n"
    mensaje += f"📊 Total: *{total} tareas pendientes*\n"
    mensaje += f"💡 Responde aquí para marcarlas como completadas"

    return mensaje


def verificar_y_enviar_alertas(bot_token, chat_id):
    """Verifica si hay que enviar alertas y las envía."""
    ahora = datetime.now(MEXICO_TZ)
    alertas = cargar_alertas_enviadas()
    tareas = obtener_tareas_pendientes()

    if not tareas:
        return

    tareas_a_alertar = {"alta": [], "media": [], "baja": []}
    hay_alertas = False

    for tarea in tareas:
        prioridad = tarea.get("prioridad", "media").lower()
        tarea_id = str(tarea.get("id", ""))
        ultima_alerta = alertas.get(tarea_id, None)

        if prioridad == "alta":
            # Cada 2 horas
            if ultima_alerta:
                ultima = datetime.fromisoformat(ultima_alerta)
                if (ahora - ultima).total_seconds() < 2 * 3600:
                    continue
            tareas_a_alertar["alta"].append(tarea)
            alertas[tarea_id] = ahora.isoformat()
            hay_alertas = True

        elif prioridad == "media":
            # Cada 4 horas
            if ultima_alerta:
                ultima = datetime.fromisoformat(ultima_alerta)
                if (ahora - ultima).total_seconds() < 4 * 3600:
                    continue
            tareas_a_alertar["media"].append(tarea)
            alertas[tarea_id] = ahora.isoformat()
            hay_alertas = True

        elif prioridad == "baja":
            # Solo a las 8 AM
            if ahora.hour == HORA_ALERTA_BAJA:
                if ultima_alerta:
                    ultima = datetime.fromisoformat(ultima_alerta)
                    # No alertar si ya se alertó hoy
                    if ultima.date() == ahora.date():
                        continue
                tareas_a_alertar["baja"].append(tarea)
                alertas[tarea_id] = ahora.isoformat()
                hay_alertas = True

    if hay_alertas:
        mensaje = formatear_alerta(tareas_a_alertar)
        enviar_alerta_telegram(bot_token, chat_id, mensaje)
        guardar_alertas_enviadas(alertas)


def iniciar_sistema_alertas(bot_token, chat_id):
    """
    Inicia el sistema de alertas en un hilo separado.
    Verifica cada 30 minutos si hay alertas pendientes.
    """
    def loop_alertas():
        print("  🔔 Sistema de alertas iniciado")
        print(f"     Alta: cada 2 hrs | Media: cada 4 hrs | Baja: 8:00 AM")

        while True:
            try:
                verificar_y_enviar_alertas(bot_token, chat_id)
            except Exception as e:
                print(f"  ⚠️ Error en alertas: {e}")

            # Verificar cada 30 minutos
            time.sleep(30 * 60)

    hilo = threading.Thread(target=loop_alertas, daemon=True)
    hilo.start()
    return hilo
