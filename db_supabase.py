"""
=============================================================
🗄️ BASE DE DATOS SUPABASE - Compartida entre todos los agentes
=============================================================

Este módulo reemplaza SQLite con Supabase para que el Dashboard
en la nube y el bot de Telegram compartan la misma base de datos.

=============================================================
"""

import os
import json
import requests
from datetime import datetime

# Configuración de Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ovfuahmjvnlpmxsospsx.supabase.co/rest/v1")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92ZnVhaG1qdm5scG14c29zcHN4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAwODk0ODksImV4cCI6MjA5NTY2NTQ4OX0.QiPqZKqwuFNXsIZHMiJ_5QXY1p9ah6KEXP3o135i0Jc")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}


# =============================================================
# TAREAS
# =============================================================

def get_tareas(estado=None):
    """Obtiene tareas, opcionalmente filtradas por estado."""
    try:
        url = f"{SUPABASE_URL}/tareas?select=*&order=id.asc"
        if estado:
            url += f"&estado=eq.{estado}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            datos = r.json()
            # Convertir a formato compatible con el dashboard (tuplas)
            return [(d["id"], d["titulo"], d.get("descripcion", ""),
                     d["estado"], d["prioridad"]) for d in datos]
        return []
    except Exception as e:
        print(f"Error Supabase get_tareas: {e}")
        return []


def add_tarea(titulo, descripcion="", prioridad="media"):
    """Agrega una nueva tarea."""
    try:
        data = {
            "titulo": titulo,
            "descripcion": descripcion,
            "prioridad": prioridad,
            "estado": "pendiente"
        }
        r = requests.post(f"{SUPABASE_URL}/tareas", headers=HEADERS,
                         json=data, timeout=10)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"Error Supabase add_tarea: {e}")
        return False


def complete_tarea(task_id):
    """Marca una tarea como completada."""
    try:
        data = {"estado": "completada"}
        r = requests.patch(f"{SUPABASE_URL}/tareas?id=eq.{task_id}",
                          headers=HEADERS, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Error Supabase complete_tarea: {e}")
        return False


# =============================================================
# CONTACTOS
# =============================================================

def get_contactos():
    """Obtiene todos los contactos."""
    try:
        r = requests.get(f"{SUPABASE_URL}/contactos?select=*&order=nombre.asc",
                        headers=HEADERS, timeout=10)
        if r.status_code == 200:
            datos = r.json()
            return [(d["id"], d["nombre"], d.get("email", ""),
                     d.get("telefono", ""), d.get("notas", "")) for d in datos]
        return []
    except Exception as e:
        print(f"Error Supabase get_contactos: {e}")
        return []


def add_contacto(nombre, email="", telefono="", notas=""):
    """Agrega un nuevo contacto."""
    try:
        data = {
            "nombre": nombre,
            "email": email,
            "telefono": telefono,
            "notas": notas
        }
        r = requests.post(f"{SUPABASE_URL}/contactos", headers=HEADERS,
                         json=data, timeout=10)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"Error Supabase add_contacto: {e}")
        return False


# =============================================================
# CONSULTAS SQL (para el agente/bot)
# =============================================================

def consultar_sql(consulta):
    """Ejecuta consultas tipo SQL traducidas a Supabase REST."""
    consulta_upper = consulta.strip().upper()

    # Bloquear operaciones peligrosas
    if any(p in consulta_upper for p in ["DROP", "DELETE", "ALTER", "TRUNCATE"]):
        return "Operación no permitida."

    try:
        # SELECT de tareas
        if "TAREAS" in consulta_upper and consulta_upper.startswith("SELECT"):
            tareas = get_tareas()
            if "PENDIENTE" in consulta_upper:
                tareas = [t for t in tareas if t[3] == "pendiente"]
            elif "COMPLETADA" in consulta_upper:
                tareas = [t for t in tareas if t[3] == "completada"]

            if not tareas:
                return "Sin resultados."

            resultado = "Columnas: id, titulo, descripcion, estado, prioridad\n\n"
            for t in tareas:
                resultado += f"{t[0]} | {t[1]} | {t[2]} | {t[3]} | {t[4]}\n"
            return resultado

        # SELECT de contactos
        elif "CONTACTOS" in consulta_upper and consulta_upper.startswith("SELECT"):
            contactos = get_contactos()
            if not contactos:
                return "Sin resultados."

            resultado = "Columnas: id, nombre, email, telefono, notas\n\n"
            for c in contactos:
                resultado += f"{c[0]} | {c[1]} | {c[2]} | {c[3]} | {c[4]}\n"
            return resultado

        # INSERT en tareas
        elif "TAREAS" in consulta_upper and "INSERT" in consulta_upper:
            # Extraer valores básicos
            import re
            values_match = re.search(r"VALUES\s*\((.+?)\)", consulta, re.IGNORECASE)
            if values_match:
                vals = [v.strip().strip("'\"") for v in values_match.group(1).split(",")]
                titulo = vals[0] if len(vals) > 0 else "Sin título"
                desc = vals[1] if len(vals) > 1 else ""
                estado = vals[2] if len(vals) > 2 else "pendiente"
                prioridad = vals[3] if len(vals) > 3 else "media"
                add_tarea(titulo, desc, prioridad)
                return "Tarea agregada exitosamente."
            return "Error: formato INSERT no reconocido."

        # INSERT en contactos
        elif "CONTACTOS" in consulta_upper and "INSERT" in consulta_upper:
            import re
            values_match = re.search(r"VALUES\s*\((.+?)\)", consulta, re.IGNORECASE)
            if values_match:
                vals = [v.strip().strip("'\"") for v in values_match.group(1).split(",")]
                nombre = vals[0] if len(vals) > 0 else "Sin nombre"
                email = vals[1] if len(vals) > 1 else ""
                telefono = vals[2] if len(vals) > 2 else ""
                notas = vals[3] if len(vals) > 3 else ""
                add_contacto(nombre, email, telefono, notas)
                return "Contacto agregado exitosamente."
            return "Error: formato INSERT no reconocido."

        # UPDATE tareas
        elif "TAREAS" in consulta_upper and "UPDATE" in consulta_upper:
            if "COMPLETADA" in consulta_upper:
                import re
                id_match = re.search(r"id\s*=\s*(\d+)", consulta)
                if id_match:
                    complete_tarea(int(id_match.group(1)))
                    return "Tarea actualizada."
            return "Update procesado."

        else:
            return f"Consulta no soportada en modo Supabase. Usa las funciones directas."

    except Exception as e:
        return f"Error: {str(e)}"
