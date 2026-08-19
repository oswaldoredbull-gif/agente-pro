"""
=============================================================
ALERTAS DE VENTAS DSS - Recordatorios por Telegram
=============================================================

6 alertas comerciales que se revisan desde el loop de 30 minutos
que ya corre en telegram_bot_memoria.py.

Punto de entrada:
    revisar_alertas()   -> revisa los JOBS y envia lo que toque

Integracion sugerida (Fase 2, con alias para no confundir modulos):
    from alertas_ventas import revisar_alertas as revisar_alertas_ventas
    ...
    revisar_alertas_ventas()

Variables de entorno: TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.
(El brief mencionaba TELEGRAM_TOKEN; el .env del proyecto usa
 TELEGRAM_BOT_TOKEN, asi que se respeta el nombre del proyecto.)
=============================================================
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv(override=True)

MEXICO_TZ = timezone(timedelta(hours=-6))
ESTADO_FILE = "alertas_ventas_enviadas.json"
VENTANA_MIN = 30          # el bot revisa cada 30 min
TIMEOUT = 15

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or ""


def _ahora():
    return datetime.now(MEXICO_TZ)


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


# =============================================================
# ESTADO (evita reenviar la misma alerta el mismo dia)
# =============================================================

def _cargar_estado():
    p = Path(ESTADO_FILE)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _guardar_estado(estado):
    try:
        with open(ESTADO_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  No se pudo guardar {ESTADO_FILE}: {e}")


# =============================================================
# ENVIO A TELEGRAM
# =============================================================

def enviar_telegram(mensaje, bot_token=None, chat_id=None):
    token = bot_token or TELEGRAM_BOT_TOKEN
    chat = chat_id or TELEGRAM_CHAT_ID

    if not token or not chat:
        print("  Alertas de ventas: falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en el .env")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": mensaje[:4000], "parse_mode": "Markdown"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return True
        print(f"  Telegram respondio {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"  Error enviando alerta de ventas: {e}")
        return False


# =============================================================
# ALERTA 1 - Prospectos nuevos sin contactar
# =============================================================

def alerta_prospectos_sin_contactar(dias=3):
    from tools_ventas import _sb_get

    corte = (_ahora() - timedelta(days=dias)).isoformat()
    ok, datos = _sb_get(
        "prospectos",
        f"select=id,nombre,telefono,ciudad,creado_en&etapa=eq.nuevo"
        f"&creado_en=lt.{corte}&order=creado_en.asc&limit=15"
    )
    if not ok or not datos:
        return None

    lineas = [f"*PROSPECTOS SIN CONTACTAR* ({len(datos)})",
              f"Llevan mas de {dias} dias en etapa 'nuevo'", ""]
    for p in datos:
        tel = p.get("telefono") or "sin telefono"
        lineas.append(f"- [{p['id']}] {p.get('nombre','')} | {p.get('ciudad','')} | {tel}")
    lineas.append("")
    lineas.append("Muevelos de etapa con actualizar_prospecto.")
    return "\n".join(lineas)


# =============================================================
# ALERTA 2 - Cotizaciones enviadas sin respuesta
# =============================================================

def alerta_cotizaciones_sin_respuesta(dias=7):
    from tools_ventas import _sb_get

    corte = (_ahora().date() - timedelta(days=dias)).isoformat()
    ok, datos = _sb_get(
        "cotizaciones",
        f"select=id,folio,total,fecha,cliente_id,prospecto_id&estatus=eq.enviada"
        f"&fecha=lt.{corte}&order=fecha.asc&limit=15"
    )
    if not ok or not datos:
        return None

    total = sum(float(c.get("total", 0) or 0) for c in datos)
    lineas = [f"*COTIZACIONES SIN RESPUESTA* ({len(datos)})",
              f"Enviadas hace mas de {dias} dias", ""]
    for c in datos:
        lineas.append(f"- {c.get('folio','')} | {c.get('fecha','')} | {_money(c.get('total', 0))}")
    lineas.append("")
    lineas.append(f"Valor detenido: *{_money(total)}*")
    return "\n".join(lineas)


# =============================================================
# ALERTA 3 - Cotizaciones por vencer
# =============================================================

def alerta_cotizaciones_por_vencer(dias_aviso=3):
    from tools_ventas import _sb_get

    ok, datos = _sb_get(
        "cotizaciones",
        "select=id,folio,total,fecha,vigencia_dias&estatus=in.(borrador,enviada)"
        "&order=fecha.asc&limit=50"
    )
    if not ok or not datos:
        return None

    hoy = _ahora().date()
    por_vencer = []
    for c in datos:
        try:
            fecha = datetime.strptime(str(c.get("fecha"))[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        vence = fecha + timedelta(days=int(c.get("vigencia_dias", 15) or 15))
        restan = (vence - hoy).days
        if 0 <= restan <= dias_aviso:
            por_vencer.append((restan, c, vence))

    if not por_vencer:
        return None

    por_vencer.sort(key=lambda x: x[0])
    lineas = [f"*COTIZACIONES POR VENCER* ({len(por_vencer)})", ""]
    for restan, c, vence in por_vencer:
        etiqueta = "vence HOY" if restan == 0 else f"vence en {restan} dia(s)"
        lineas.append(f"- {c.get('folio','')} | {_money(c.get('total', 0))} | {etiqueta} ({vence})")
    lineas.append("")
    lineas.append("Da seguimiento o extiende la vigencia.")
    return "\n".join(lineas)


# =============================================================
# ALERTA 4 - Entregas programadas para hoy
# =============================================================

def alerta_entregas_hoy():
    from tools_ventas import _sb_get

    hoy = _ahora().date().isoformat()
    ok, datos = _sb_get(
        "entregas",
        f"select=id,cliente_id,fecha_programada,estatus,guia,notas"
        f"&fecha_programada=lte.{hoy}&estatus=in.(programada,en_ruta)"
        f"&order=fecha_programada.asc&limit=15"
    )
    if not ok or not datos:
        return None

    lineas = [f"*ENTREGAS PENDIENTES* ({len(datos)})", ""]
    for e in datos:
        atrasada = str(e.get("fecha_programada", ""))[:10] < hoy
        marca = " ATRASADA" if atrasada else ""
        nombre = "cliente " + str(e.get("cliente_id"))
        ok_c, cli = _sb_get("clientes", f"select=nombre&id=eq.{e.get('cliente_id')}")
        if ok_c and cli:
            nombre = cli[0].get("nombre", nombre)
        lineas.append(f"- {nombre} | {e.get('fecha_programada','')} | {e.get('estatus','')}{marca}")
        if e.get("guia"):
            lineas.append(f"    guia: {e['guia']}")
    return "\n".join(lineas)


# =============================================================
# ALERTA 5 - Resumen semanal del embudo
# =============================================================

def alerta_resumen_semanal():
    from tools_ventas import metricas_ventas, _sb_listo

    if not _sb_listo():
        return None

    texto = metricas_ventas()
    # Si ninguna de las dos secciones pudo leerse, no mandamos ruido.
    if "no disponible" in texto:
        return None
    return "*RESUMEN SEMANAL DE VENTAS*\n\n```\n" + texto + "\n```"


# =============================================================
# ALERTA 6 - Renovaciones proximas (brief 2.3)
# =============================================================

def alerta_renovaciones(dias=45):
    from licencias import obtener_renovaciones, renovaciones_proximas

    ok, datos = obtener_renovaciones(dias)
    if not ok or not datos:
        return None

    return ("*RENOVACIONES DE LICENCIAS*\n\n```\n"
            + renovaciones_proximas(dias) + "\n```")


# =============================================================
# CALENDARIO DE ALERTAS
# dia: None = todos los dias | 0 = lunes ... 6 = domingo
# =============================================================

JOBS = [
    {"nombre": "entregas_hoy",              "dia": None, "hora": 7,  "minuto": 30, "func": alerta_entregas_hoy},
    {"nombre": "prospectos_sin_contactar",  "dia": None, "hora": 9,  "minuto": 0,  "func": alerta_prospectos_sin_contactar},
    {"nombre": "cotizaciones_sin_respuesta","dia": None, "hora": 9,  "minuto": 30, "func": alerta_cotizaciones_sin_respuesta},
    {"nombre": "cotizaciones_por_vencer",   "dia": None, "hora": 10, "minuto": 0,  "func": alerta_cotizaciones_por_vencer},
    {"nombre": "resumen_semanal",           "dia": 0,    "hora": 8,  "minuto": 0,  "func": alerta_resumen_semanal},
    {"nombre": "renovaciones",              "dia": 0,    "hora": 8,  "minuto": 30, "func": alerta_renovaciones},
]


def _toca_ahora(job, ahora):
    """True si el job cae dentro de la ventana de 30 min que se esta revisando."""
    if job["dia"] is not None and ahora.weekday() != job["dia"]:
        return False
    if ahora.hour != job["hora"]:
        return False
    inicio = job["minuto"]
    return inicio <= ahora.minute < inicio + VENTANA_MIN


# =============================================================
# PUNTO DE ENTRADA
# =============================================================

def revisar_alertas(bot_token=None, chat_id=None, forzar=None):
    """
    Revisa los JOBS y envia por Telegram los que toquen en esta ventana.
    forzar: nombre de un job (o "todas") para dispararlo ignorando el horario.
    Devuelve la lista de nombres de alertas enviadas.
    """
    ahora = _ahora()
    estado = _cargar_estado()
    hoy = ahora.date().isoformat()
    enviadas = []

    for job in JOBS:
        nombre = job["nombre"]

        if forzar:
            if forzar not in ("todas", nombre):
                continue
        else:
            if not _toca_ahora(job, ahora):
                continue
            if estado.get(nombre) == hoy:
                continue

        try:
            mensaje = job["func"]()
        except Exception as e:
            print(f"  Error en alerta de ventas '{nombre}': {e}")
            continue

        if not mensaje:
            if not forzar:
                estado[nombre] = hoy
            continue

        if enviar_telegram(mensaje, bot_token, chat_id):
            enviadas.append(nombre)
            if not forzar:
                estado[nombre] = hoy

    if enviadas and not forzar:
        _guardar_estado(estado)

    if enviadas:
        print(f"  Alertas de ventas enviadas: {', '.join(enviadas)}")

    return enviadas


def iniciar_sistema_alertas_ventas(bot_token=None, chat_id=None):
    """
    Arranca un hilo que revisa las alertas de ventas cada 30 minutos.

    Se usa en paralelo a iniciar_sistema_alertas() de alertas.py, que tiene
    su propio hilo. El brief pedia meter la llamada 'dentro del loop de 30
    minutos de telegram_bot_memoria.py', pero ese loop vive en alertas.py,
    que el brief prohibe modificar. Un hilo hermano logra lo mismo sin
    tocar el archivo existente.
    """
    import threading
    import time

    def loop():
        print("  Sistema de alertas de VENTAS iniciado (revision cada 30 min)")
        while True:
            try:
                revisar_alertas(bot_token, chat_id)
            except Exception as e:
                print(f"  Error en loop de alertas de ventas: {e}")
            time.sleep(VENTANA_MIN * 60)

    hilo = threading.Thread(target=loop, daemon=True)
    hilo.start()
    return hilo


if __name__ == "__main__":
    print("=" * 55)
    print("VERIFICACION alertas_ventas.py")
    print("=" * 55)
    print(f"\nTELEGRAM_BOT_TOKEN: {'OK' if TELEGRAM_BOT_TOKEN else 'FALTA'}")
    print(f"TELEGRAM_CHAT_ID  : {'OK' if TELEGRAM_CHAT_ID else 'FALTA'}")
    print(f"Alertas registradas: {len(JOBS)}")

    ahora = _ahora()
    print(f"\nHora Mexico: {ahora.strftime('%A %H:%M')}")
    print("\nCalendario:")
    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    for j in JOBS:
        cuando = "diario" if j["dia"] is None else dias[j["dia"]]
        marca = "  <-- toca ahora" if _toca_ahora(j, ahora) else ""
        print(f"  {j['nombre']:<28} {cuando:<10} {j['hora']:02d}:{j['minuto']:02d}{marca}")

    print("\nGenerando mensajes en seco (sin enviar a Telegram):")
    for j in JOBS:
        try:
            msg = j["func"]()
            print(f"  {j['nombre']:<28} -> {'con contenido' if msg else 'sin novedades'}")
        except Exception as e:
            print(f"  {j['nombre']:<28} -> ERROR: {e}")
