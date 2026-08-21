"""
=============================================================
LICENCIAS DE SOFTWARE - Digital Software Solutions (DSS)
=============================================================

Lee el catalogo REAL de licencias desde el backend de
software.dsstonermx.com (proyecto Supabase 'ds-software'), que a su
vez se sincroniza solo con CT Internacional.

No hay catalogo hardcodeado: los precios y costos salen siempre de
la fuente. Si CT cambia precios, el agente lo ve en la siguiente
consulta sin tocar codigo.

Acceso: Edge Function 'catalogo-interno', autenticada con el header
x-dss-secret. Esa funcion solo puede leer la tabla de productos, no
el resto de la base.

Exporta:
    TOOLS_LICENCIAS     -> lista de tool schemas
    FUNCIONES_LICENCIAS -> dict {nombre_tool: callable(args) -> str}
    renovaciones_proximas(dias) -> texto, para alertas_ventas.py
    obtener_renovaciones(dias)  -> (ok, lista), para uso programatico

Variables de entorno:
    DSS_CATALOGO_URL     https://<ref>.supabase.co/functions/v1/catalogo-interno
    DSS_CATALOGO_SECRET  el secreto compartido con la Edge Function

IMPORTANTE (regla del brief):
    La importacion de cotizador_pdf ocurre DENTRO de cotizar_licencias,
    nunca a nivel de modulo, para evitar el import circular.
=============================================================
"""

import os
import requests
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv(override=True)

MEXICO_TZ = timezone(timedelta(hours=-6))
TIMEOUT = 20

CATALOGO_URL = (os.getenv("DSS_CATALOGO_URL") or "").rstrip("/")
CATALOGO_SECRET = os.getenv("DSS_CATALOGO_SECRET") or ""

# Margen minimo saludable antes de levantar advertencia.
# El sync de CT aplica 20% por defecto, asi que por debajo de 15 hay algo raro.
MARGEN_MINIMO_PCT = 15.0

# Periodicidad por defecto cuando el catalogo no la especifica.
PERIODICIDAD_POR_CATEGORIA = {
    "seguridad": "anual",
    "productividad": "anual",
    "facturación electrónica": "anual",
    "facturacion electronica": "anual",
    "punto de venta": "perpetua",
    "sistemas operativos": "perpetua",
}

_cache = {"datos": None, "hora": None}
CACHE_MIN = 10


def _ahora():
    return datetime.now(MEXICO_TZ)


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _catalogo_listo():
    return bool(CATALOGO_URL and CATALOGO_SECRET)


# =============================================================
# ACCESO AL CATALOGO
# =============================================================

def consultar_catalogo(buscar="", categoria="", limite=50, usar_cache=True):
    """
    Consulta la Edge Function y devuelve (ok, lista_de_productos | mensaje).
    Cachea la consulta completa unos minutos para no golpear la funcion
    en cada tool call del agente.
    """
    if not _catalogo_listo():
        return False, ("Catalogo de licencias no configurado: faltan "
                       "DSS_CATALOGO_URL o DSS_CATALOGO_SECRET en el .env")

    clave = (buscar.lower(), categoria.lower(), limite)
    if usar_cache and _cache["datos"] and _cache["hora"]:
        edad = (_ahora() - _cache["hora"]).total_seconds() / 60
        if edad < CACHE_MIN and _cache["datos"].get("clave") == clave:
            return True, _cache["datos"]["productos"]

    params = {"limite": limite}
    if buscar:
        params["q"] = buscar
    if categoria:
        params["categoria"] = categoria

    try:
        r = requests.get(CATALOGO_URL, params=params,
                         headers={"x-dss-secret": CATALOGO_SECRET},
                         timeout=TIMEOUT)
    except Exception as e:
        return False, f"No se pudo conectar con el catalogo: {e}"

    if r.status_code == 401:
        return False, "El catalogo rechazo el secreto. Revisa DSS_CATALOGO_SECRET."
    if r.status_code != 200:
        return False, f"El catalogo respondio {r.status_code}: {r.text[:200]}"

    try:
        payload = r.json()
    except Exception:
        return False, "El catalogo devolvio una respuesta que no es JSON."

    if not payload.get("ok"):
        return False, f"Error del catalogo: {payload.get('error', 'sin detalle')}"

    productos = payload.get("productos", [])
    _cache["datos"] = {"clave": clave, "productos": productos}
    _cache["hora"] = _ahora()
    return True, productos


def buscar_producto(sku):
    """Devuelve (ok, producto) buscando por SKU exacto."""
    ok, datos = consultar_catalogo(buscar=sku, limite=50, usar_cache=False)
    if not ok:
        return False, datos
    exacto = [p for p in datos if str(p.get("sku", "")).upper() == str(sku).upper()]
    if exacto:
        return True, exacto[0]
    return False, f"No encontre el SKU '{sku}' en el catalogo."


def _periodicidad(producto):
    cat = str(producto.get("categoria", "")).strip().lower()
    return PERIODICIDAD_POR_CATEGORIA.get(cat, "anual")


def calcular_margen(costo, precio, puestos=1):
    """Devuelve dict con costo, precio, margen y margen_pct para N puestos."""
    try:
        puestos = max(1, int(puestos))
    except (TypeError, ValueError):
        puestos = 1

    costo_total = round(float(costo) * puestos, 2)
    precio_total = round(float(precio) * puestos, 2)
    margen = round(precio_total - costo_total, 2)
    margen_pct = round((margen / precio_total) * 100, 1) if precio_total else 0.0

    return {
        "puestos": puestos,
        "costo_total": costo_total,
        "precio_total": precio_total,
        "margen": margen,
        "margen_pct": margen_pct,
        "alerta_margen": margen_pct < MARGEN_MINIMO_PCT,
    }


# =============================================================
# 1. LISTAR / BUSCAR EN EL CATALOGO
# =============================================================

def listar_paquetes_licencias(software="", puestos=1, categoria="", limite=15):
    """Busca en el catalogo real de licencias y muestra precio y margen."""
    try:
        puestos = max(1, int(puestos))
    except (TypeError, ValueError):
        puestos = 1
    try:
        limite = max(1, min(int(limite), 50))
    except (TypeError, ValueError):
        limite = 15

    ok, datos = consultar_catalogo(buscar=software, categoria=categoria, limite=limite)
    if not ok:
        return f"No se pudo leer el catalogo. {datos}"
    if not datos:
        filtro = software or categoria or "todo"
        return f"Sin licencias que coincidan con '{filtro}'."

    lineas = [f"CATALOGO DE LICENCIAS DSS ({len(datos)} resultados"
              + (f", para {puestos} puesto(s)" if puestos > 1 else "") + ", precios sin IVA)",
              "=" * 74]

    for p in datos:
        m = calcular_margen(p.get("costo", 0), p.get("precio", 0), puestos)
        promo = "  [PROMOCION]" if p.get("en_promocion") else ""
        lineas.append(f"\n{p.get('nombre', 'Sin nombre')[:62]}{promo}")
        lineas.append(f"  SKU: {p.get('sku')} | {p.get('marca', '')} | {p.get('categoria', '')}")
        lineas.append(
            f"  Costo: {_money(m['costo_total'])} | "
            f"Venta: {_money(m['precio_total'])} | "
            f"Margen: {_money(m['margen'])} ({m['margen_pct']}%)"
            + ("  << margen bajo" if m["alerta_margen"] else "")
        )
        if p.get("disponibilidad") and p["disponibilidad"] != "disponible":
            lineas.append(f"  Disponibilidad: {p['disponibilidad']}")

    lineas.append("")
    lineas.append("Para cotizar, usa cotizar_licencias con el SKU.")
    return "\n".join(lineas)


# =============================================================
# 2. COTIZAR LICENCIAS
# =============================================================

def cotizar_licencias(paquetes, cliente_id=None, prospecto_id=None,
                      generar_pdf=True, vigencia_dias=15, notas=""):
    """
    Cotiza uno o varios SKUs del catalogo real.
    paquetes: lista de dicts {paquete: SKU, puestos: N} o lista de SKUs (str).

    El import de cotizador_pdf va aqui adentro a proposito (import circular).
    """
    if not paquetes:
        return "Error: indica al menos un SKU a cotizar."
    if isinstance(paquetes, str):
        paquetes = [paquetes]

    items = []
    costo_acum = 0.0
    precio_acum = 0.0
    detalle = []

    for entrada in paquetes:
        if isinstance(entrada, str):
            sku, puestos = entrada, 1
        else:
            sku = entrada.get("paquete") or entrada.get("sku") or entrada.get("clave") or ""
            puestos = entrada.get("puestos", 1)

        ok, p = buscar_producto(str(sku).strip())
        if not ok:
            return (f"{p}\n\nUsa listar_paquetes_licencias para ver los SKUs disponibles.")

        m = calcular_margen(p.get("costo", 0), p.get("precio", 0), puestos)

        items.append({
            "descripcion": f"{p.get('nombre')} ({p.get('sku')})",
            "cantidad": m["puestos"],
            "precio_unitario": float(p.get("precio", 0)),
            "costo_unitario": float(p.get("costo", 0)),
        })

        costo_acum += m["costo_total"]
        precio_acum += m["precio_total"]
        detalle.append((p.get("nombre", ""), p.get("sku"), m, bool(p.get("en_promocion"))))

    margen = round(precio_acum - costo_acum, 2)
    margen_pct = round((margen / precio_acum) * 100, 1) if precio_acum else 0.0

    resumen = ["RESUMEN DE MARGEN", "-" * 70]
    for nombre, sku, m, promo in detalle:
        etiqueta = f"{nombre[:34]}{' [promo]' if promo else ''}"
        resumen.append(
            f"  {etiqueta:<42} {m['puestos']:>3}u  "
            f"{_money(m['precio_total']):>13}  {m['margen_pct']:>5}%"
        )
    resumen.append("-" * 70)
    resumen.append(f"  Costo total : {_money(costo_acum)}")
    resumen.append(f"  Venta total : {_money(precio_acum)} (sin IVA)")
    resumen.append(f"  Margen      : {_money(margen)} ({margen_pct}%)")
    if margen_pct < MARGEN_MINIMO_PCT:
        resumen.append(f"  AVISO: margen por debajo del minimo de {MARGEN_MINIMO_PCT}%")

    if not notas:
        notas = ("Licencias originales adquiridas a mayorista autorizado. "
                 "Entrega digital de la clave de activacion.")

    if generar_pdf:
        from cotizador_pdf import cotizar_pdf
        salida = cotizar_pdf(items=items, cliente_id=cliente_id,
                             prospecto_id=prospecto_id,
                             vigencia_dias=vigencia_dias, notas=notas)
    else:
        from tools_ventas import cotizar_texto
        salida = cotizar_texto(items, cliente_id, prospecto_id,
                               vigencia_dias, notas)

    return f"{salida}\n\n" + "\n".join(resumen)


# =============================================================
# 3. REGISTRAR LICENCIA VENDIDA
# =============================================================

def registrar_licencia(cliente_id, paquete, puestos=1, fecha_inicio=None,
                       periodicidad="", renovacion_auto=False,
                       clave_activacion="", notas=""):
    """Da de alta una licencia vendida y calcula su fecha de vencimiento."""
    from tools_ventas import _sb_post

    try:
        cid = int(cliente_id)
    except (TypeError, ValueError):
        return "Error: cliente_id debe ser un numero."

    ok, p = buscar_producto(str(paquete).strip())
    if not ok:
        return f"{p}\n\nUsa listar_paquetes_licencias para ver los SKUs disponibles."

    m = calcular_margen(p.get("costo", 0), p.get("precio", 0), puestos)

    per = (periodicidad or _periodicidad(p)).strip().lower()
    if per not in ("mensual", "anual", "perpetua"):
        return f"Error: periodicidad invalida '{per}'. Usa mensual, anual o perpetua."

    if fecha_inicio:
        try:
            inicio = datetime.strptime(str(fecha_inicio)[:10], "%Y-%m-%d").date()
        except ValueError:
            return "Error: fecha_inicio debe tener formato AAAA-MM-DD."
    else:
        inicio = _ahora().date()

    dias = {"mensual": 30, "anual": 365, "perpetua": 3650}[per]
    fin = inicio + timedelta(days=dias)

    data = {
        "cliente_id": cid,
        "paquete": p.get("sku"),
        "software": p.get("nombre", "")[:200],
        "edicion": p.get("categoria", ""),
        "puestos": m["puestos"],
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": fin.isoformat(),
        "periodicidad": per,
        "costo_total": m["costo_total"],
        "precio_total": m["precio_total"],
        "renovacion_auto": bool(renovacion_auto),
        "estatus": "activa",
        "clave_activacion": clave_activacion,
        "notas": notas,
    }

    ok_ins, res = _sb_post("licencias_activas", data)
    if not ok_ins:
        return f"No se pudo registrar la licencia. {res}"

    lid = res[0]["id"] if isinstance(res, list) and res else None
    return (f"Licencia registrada (id {lid}): {p.get('nombre')} x{m['puestos']}\n"
            f"Vigencia: {inicio.isoformat()} a {fin.isoformat()} ({per})\n"
            f"Venta: {_money(m['precio_total'])} | Margen: {_money(m['margen'])} ({m['margen_pct']}%)")


# =============================================================
# 4. RENOVACIONES PROXIMAS
# =============================================================

def obtener_renovaciones(dias=45):
    """(ok, lista) de licencias que vencen en los proximos N dias."""
    from tools_ventas import _sb_get

    try:
        dias = max(1, min(int(dias), 365))
    except (TypeError, ValueError):
        dias = 45

    ok, datos = _sb_get(
        "renovaciones",
        f"select=*&dias_restantes=lte.{dias}&dias_restantes=gte.0&order=dias_restantes.asc"
    )
    if not ok:
        return False, datos
    return True, datos


def renovaciones_proximas(dias=45):
    """Texto con las licencias que vencen en los proximos N dias."""
    ok, datos = obtener_renovaciones(dias)
    if not ok:
        return f"No se pudieron leer las renovaciones. {datos}"
    if not datos:
        return f"Sin renovaciones en los proximos {dias} dias."

    lineas = [f"RENOVACIONES EN LOS PROXIMOS {dias} DIAS ({len(datos)})", "=" * 66]
    total = 0.0

    for r in datos:
        total += float(r.get("precio_total", 0) or 0)
        urgencia = "URGENTE" if int(r.get("dias_restantes", 99) or 99) <= 15 else ""
        lineas.append(
            f"[{r.get('dias_restantes')} dias] {r.get('cliente', 'Sin cliente')} | "
            f"{str(r.get('software', ''))[:40]} x{r.get('puestos', 1)} | "
            f"vence {r.get('fecha_fin', '')} | {_money(r.get('precio_total', 0))} "
            f"(margen {r.get('margen_pct', 0)}%) {urgencia}".rstrip()
        )
        if r.get("renovacion_auto"):
            lineas.append("    renovacion automatica activada")
        elif r.get("telefono"):
            lineas.append(f"    contacto: {r['telefono']}")

    lineas.append("=" * 66)
    lineas.append(f"Valor total en juego: {_money(total)}")
    return "\n".join(lineas)


# =============================================================
# DEFINICION DE HERRAMIENTAS PARA CLAUDE
# =============================================================

TOOLS_LICENCIAS = [
    {
        "name": "listar_paquetes_licencias",
        "description": (
            "Busca en el catalogo real de licencias de software que vende DSS, sincronizado con "
            "CT Internacional (Microsoft 365, Office, Windows, antivirus Kaspersky/Norton/ESET, "
            "facturacion CFDI Aspel, punto de venta). Muestra SKU, costo, precio de venta y margen. "
            "Usala cuando pregunten que licencias hay, cuanto cuestan o cuanto se gana con ellas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "software": {"type": "string", "description": "Texto a buscar en nombre, marca o SKU (ej: Microsoft 365, Kaspersky)", "default": ""},
                "categoria": {"type": "string", "description": "Categoria: Seguridad, Productividad, Facturacion Electronica, Punto de Venta, Sistemas Operativos", "default": ""},
                "puestos": {"type": "integer", "description": "Numero de puestos o equipos para calcular el total", "default": 1},
                "limite": {"type": "integer", "description": "Maximo de resultados (1-50)", "default": 15}
            },
            "required": []
        }
    },
    {
        "name": "cotizar_licencias",
        "description": (
            "Cotiza uno o varios SKUs del catalogo de licencias para un cliente, genera el PDF y "
            "muestra el desglose de margen. Primero busca el SKU con listar_paquetes_licencias."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paquetes": {
                    "type": "array",
                    "description": "SKUs a cotizar",
                    "items": {
                        "type": "object",
                        "properties": {
                            "paquete": {"type": "string", "description": "SKU del catalogo (ej: SOFMSC1910)"},
                            "puestos": {"type": "integer", "description": "Numero de puestos o equipos", "default": 1}
                        },
                        "required": ["paquete"]
                    }
                },
                "cliente_id": {"type": "integer", "description": "ID del cliente"},
                "prospecto_id": {"type": "integer", "description": "ID del prospecto, si aun no es cliente"},
                "generar_pdf": {"type": "boolean", "description": "Generar el PDF de la cotizacion", "default": True},
                "vigencia_dias": {"type": "integer", "description": "Dias de vigencia de la cotizacion", "default": 15},
                "notas": {"type": "string", "description": "Notas o condiciones", "default": ""}
            },
            "required": ["paquetes"]
        }
    },
    {
        "name": "registrar_licencia",
        "description": (
            "Registra una licencia vendida a un cliente, calcula la fecha de vencimiento segun la "
            "periodicidad y guarda el margen real. Usala cuando se cierre la venta de una licencia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {"type": "integer", "description": "ID del cliente"},
                "paquete": {"type": "string", "description": "SKU del catalogo"},
                "puestos": {"type": "integer", "description": "Numero de puestos o equipos", "default": 1},
                "fecha_inicio": {"type": "string", "description": "Fecha de inicio AAAA-MM-DD (hoy si se omite)", "default": ""},
                "periodicidad": {"type": "string", "description": "mensual, anual o perpetua. Si se omite se infiere de la categoria", "default": ""},
                "renovacion_auto": {"type": "boolean", "description": "Si la licencia se renueva sola", "default": False},
                "clave_activacion": {"type": "string", "description": "Clave o numero de orden del mayorista", "default": ""},
                "notas": {"type": "string", "description": "Notas", "default": ""}
            },
            "required": ["cliente_id", "paquete"]
        }
    },
    {
        "name": "renovaciones_proximas",
        "description": (
            "Lista las licencias vendidas que vencen en los proximos N dias, con cliente, monto y margen. "
            "Usala cuando pregunten que renovaciones vienen o donde hay ingreso recurrente en riesgo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {"type": "integer", "description": "Horizonte en dias (1-365)", "default": 45}
            },
            "required": []
        }
    },
]


FUNCIONES_LICENCIAS = {
    "listar_paquetes_licencias": lambda a: listar_paquetes_licencias(
        a.get("software", ""), a.get("puestos", 1),
        a.get("categoria", ""), a.get("limite", 15)),
    "cotizar_licencias": lambda a: cotizar_licencias(
        a["paquetes"], a.get("cliente_id"), a.get("prospecto_id"),
        a.get("generar_pdf", True), a.get("vigencia_dias", 15), a.get("notas", "")),
    "registrar_licencia": lambda a: registrar_licencia(
        a["cliente_id"], a["paquete"], a.get("puestos", 1),
        a.get("fecha_inicio"), a.get("periodicidad", ""),
        a.get("renovacion_auto", False), a.get("clave_activacion", ""),
        a.get("notas", "")),
    "renovaciones_proximas": lambda a: renovaciones_proximas(a.get("dias", 45)),
}


if __name__ == "__main__":
    print("=" * 60)
    print("VERIFICACION licencias.py")
    print("=" * 60)
    print(f"\nDSS_CATALOGO_URL    : {'OK' if CATALOGO_URL else 'FALTA'}")
    print(f"DSS_CATALOGO_SECRET : {'OK' if CATALOGO_SECRET else 'FALTA'}")
    print(f"Tools de licencias  : {len(TOOLS_LICENCIAS)}")

    if not _catalogo_listo():
        print("\nAgrega DSS_CATALOGO_URL y DSS_CATALOGO_SECRET al .env")
        raise SystemExit(1)

    ok, datos = consultar_catalogo(limite=300, usar_cache=False)
    if not ok:
        print(f"\nFALLO: {datos}")
        raise SystemExit(1)

    print(f"\nCatalogo OK: {len(datos)} licencias activas")
    cats = {}
    for p in datos:
        c = p.get("categoria", "sin categoria")
        cats[c] = cats.get(c, 0) + 1
    print("\nPor categoria:")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {c:<28} {n:>4}")

    print()
    print(listar_paquetes_licencias("Microsoft 365", puestos=5))
