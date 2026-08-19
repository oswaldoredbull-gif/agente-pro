"""
=============================================================
SISTEMA DE ALERTAS - Recordatorios por Telegram
=============================================================

Envia recordatorios automaticos segun la prioridad:
  Alta    = cada 2 horas
  Media   = cada 4 horas
  Baja    = dia siguiente a las 8:00 AM (ventana de 30 min)

=============================================================
"""

import os
import time
import json
import threading
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

MEXICO_TZ = timezone(timedelta(hours=-6))
ALERTAS_FILE = "alertas_enviadas.json"
HORA_ALERTA_BAJA = 8
VENTANA_BAJA_MIN = 30


def _ahora_mexico():
    return datetime.now(MEXICO_TZ)


def _parse_fecha(s):
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MEXICO_TZ)
    return dt


def cargar_alertas_enviadas():
    if Path(ALERTAS_FILE).exists():
        try:
            with open(ALERTAS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def guardar_alertas_enviadas(alertas):
    try:
        with open(ALERTAS_FILE, "w") as f:
            json.dump(alertas, f, indent=2)
    except Exception as e:
        print(f"  No se pudo guardar alertas_enviadas.json: {e}")


def obtener_tareas_pendientes():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if supabase_url and supabase_key:
        try:
            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json"
            }
            url = supabase_url.rstrip("/") + "/rest/v1/tareas?select=*&estado=eq.pendiente&order=id.asc"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            else:
                print(f"  Supabase respondio {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"  Error obteniendo tareas de Supabase: {e}")
        return []
    else:
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
        except Exception as e:
            print(f"  Error obteniendo tareas de SQLite: {e}")
            return []


def enviar_alerta_telegram(bot_token, chat_id, mensaje):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": mensaje,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, json=data, timeout=10)
        if r.status_code == 200:
            return True
        else:
            print(f"  Telegram respondio {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  Error enviando alerta Telegram: {e}")
        return False


def formatear_alerta(tareas_por_prioridad):
    ahora = _ahora_mexico()
    hora_str = ahora.strftime("%H:%M")

    mensaje = f"*RECORDATORIO DE TAREAS*\n"
    mensaje += f"Hora: {hora_str} hrs\n"
    mensaje += "-----------------\n\n"

    total = 0

    if tareas_por_prioridad.get("alta"):
        mensaje += "*PRIORIDAD ALTA* (cada 2 hrs)\n"
        for t in tareas_por_prioridad["alta"]:
            mensaje += f"  - {t['titulo']}\n"
            total += 1
        mensaje += "\n"

    if tareas_por_prioridad.get("media"):
        mensaje += "*PRIORIDAD MEDIA* (cada 4 hrs)\n"
        for t in tareas_por_prioridad["media"]:
            mensaje += f"  - {t['titulo']}\n"
            total += 1
        mensaje += "\n"

    if tareas_por_prioridad.get("baja"):
        mensaje += "*PRIORIDAD BAJA*\n"
        for t in tareas_por_prioridad["baja"]:
            mensaje += f"  - {t['titulo']}\n"
            total += 1
        mensaje += "\n"

    mensaje += f"-----------------\n"
    mensaje += f"Total: *{total} tareas pendientes*\n"
    mensaje += f"Responde aqui para marcarlas como completadas"

    return mensaje


def verificar_y_enviar_alertas(bot_token, chat_id):
    ahora = _ahora_mexico()
    alertas = cargar_alertas_enviadas()
    tareas = obtener_tareas_pendientes()

    if not tareas:
        return

    tareas_a_alertar = {"alta": [], "media": [], "baja": []}
    hay_alertas = False

    for tarea in tareas:
        prioridad = (tarea.get("prioridad") or "media").lower()
        tarea_id = str(tarea.get("id", ""))
        ultima_str = alertas.get(tarea_id)

        if prioridad == "alta":
            if ultima_str:
                ultima = _parse_fecha(ultima_str)
                if (ahora - ultima).total_seconds() < 2 * 3600:
                    continue
            tareas_a_alertar["alta"].append(tarea)
            alertas[tarea_id] = ahora.isoformat()
            hay_alertas = True

        elif prioridad == "media":
            if ultima_str:
                ultima = _parse_fecha(ultima_str)
                if (ahora - ultima).total_seconds() < 4 * 3600:
                    continue
            tareas_a_alertar["media"].append(tarea)
            alertas[tarea_id] = ahora.isoformat()
            hay_alertas = True

        elif prioridad == "baja":
            hora_ok = (ahora.hour == HORA_ALERTA_BAJA and
                       ahora.minute < VENTANA_BAJA_MIN)
            if not hora_ok:
                continue
            if ultima_str:
                ultima = _parse_fecha(ultima_str)
                if ultima.date() == ahora.date():
                    continue
            tareas_a_alertar["baja"].append(tarea)
            alertas[tarea_id] = ahora.isoformat()
            hay_alertas = True

    if hay_alertas:
        mensaje = formatear_alerta(tareas_a_alertar)
        ok = enviar_alerta_telegram(bot_token, chat_id, mensaje)
        if ok:
            guardar_alertas_enviadas(alertas)
            print(f"  Alertas enviadas: alta={len(tareas_a_alertar['alta'])} media={len(tareas_a_alertar['media'])} baja={len(tareas_a_alertar['baja'])}")
        else:
            print("  No se pudieron enviar las alertas")


def iniciar_sistema_alertas(bot_token, chat_id):
    def loop_alertas():
        print("  Sistema de alertas iniciado")
        print("     Alta: cada 2 hrs | Media: cada 4 hrs | Baja: 8:00-8:30 AM")

        while True:
            try:
                verificar_y_enviar_alertas(bot_token, chat_id)
            except Exception as e:
                print(f"  Error en loop de alertas: {e}")

            time.sleep(30 * 60)

    hilo = threading.Thread(target=loop_alertas, daemon=True)
    hilo.start()
    return hilo
