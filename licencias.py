"""
=============================================================
LICENCIAS DE SOFTWARE - Digital Software Solutions (DSS)
=============================================================

Catalogo de paquetes de licencias originales (compradas a mayorista
autorizado), calculo de margen, alta de licencias vendidas y control
de renovaciones.

Exporta:
    TOOLS_LICENCIAS     -> lista de tool schemas
    FUNCIONES_LICENCIAS -> dict {nombre_tool: callable(args) -> str}
    renovaciones_proximas(dias) -> texto, para alertas_ventas.py
    obtener_renovaciones(dias)  -> (ok, lista), para uso programatico

IMPORTANTE (regla del brief):
    La importacion de cotizador_pdf ocurre DENTRO de cotizar_licencias,
    nunca a nivel de modulo, para evitar el import circular.
=============================================================
"""

from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv(override=True)

MEXICO_TZ = timezone(timedelta(hours=-6))
IVA = 0.16

# Margen minimo saludable antes de levantar advertencia
MARGEN_MINIMO_PCT = 15.0


# =============================================================
# CATALOGO DE PAQUETES
# costo = precio del mayorista | precio = precio de lista DSS (sin IVA)
# Ajusta estos valores cuando cambie la lista del mayorista.
# =============================================================

PAQUETES = {
    "m365_business_basic": {
        "nombre": "Microsoft 365 Business Basic",
        "software": "Microsoft 365",
        "edicion": "Business Basic",
        "periodicidad": "anual",
        "costo": 1450.00,
        "precio": 1990.00,
        "descripcion": "Correo Exchange 50 GB, Teams, OneDrive 1 TB, apps web. Por usuario/ano.",
    },
    "m365_business_standard": {
        "nombre": "Microsoft 365 Business Standard",
        "software": "Microsoft 365",
        "edicion": "Business Standard",
        "periodicidad": "anual",
        "costo": 3050.00,
        "precio": 4190.00,
        "descripcion": "Todo lo de Basic mas apps de escritorio Office. Por usuario/ano.",
    },
    "m365_business_premium": {
        "nombre": "Microsoft 365 Business Premium",
        "software": "Microsoft 365",
        "edicion": "Business Premium",
        "periodicidad": "anual",
        "costo": 5200.00,
        "precio": 7150.00,
        "descripcion": "Standard mas Intune y Defender for Business. Por usuario/ano.",
    },
    "office_ltsc_2024": {
        "nombre": "Office LTSC Standard 2024",
        "software": "Office",
        "edicion": "LTSC Standard 2024",
        "periodicidad": "perpetua",
        "costo": 6800.00,
        "precio": 8900.00,
        "descripcion": "Licencia perpetua por equipo. Word, Excel, PowerPoint, Outlook.",
    },
    "windows_11_pro": {
        "nombre": "Windows 11 Pro OEM",
        "software": "Windows",
        "edicion": "11 Pro",
        "periodicidad": "perpetua",
        "costo": 2100.00,
        "precio": 2850.00,
        "descripcion": "Licencia OEM perpetua por equipo.",
    },
    "antivirus_endpoint": {
        "nombre": "Antivirus Endpoint Protection",
        "software": "Endpoint Protection",
        "edicion": "Business",
        "periodicidad": "anual",
        "costo": 480.00,
        "precio": 720.00,
        "descripcion": "Proteccion por equipo, consola centralizada. Por equipo/ano.",
    },
    "respaldo_nube_1tb": {
        "nombre": "Respaldo en nube 1 TB",
        "software": "Backup",
        "edicion": "1 TB",
        "periodicidad": "anual",
        "costo": 1900.00,
        "precio": 2790.00,
        "descripcion": "Respaldo automatico y restauracion. Por licencia/ano.",
    },
    "acrobat_pro": {
        "nombre": "Acrobat Pro",
        "software": "Acrobat",
        "edicion": "Pro",
        "periodicidad": "anual",
        "costo": 4300.00,
        "precio": 5750.00,
        "descripcion": "Edicion, firma y OCR de PDF. Por usuario/ano.",
    },
}


def _ahora():
    return datetime.now(MEXICO_TZ)


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


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
# 1. LISTAR PAQUETES
# =============================================================

def listar_paquetes_licencias(software="", puestos=1):
    """Muestra el catalogo de paquetes con precio y margen para N puestos."""
    try:
        puestos = max(1, int(puestos))
    except (TypeError, ValueError):
        puestos = 1

    filtro = (software or "").strip().lower()
    encontrados = [
        (clave, p) for clave, p in PAQUETES.items()
        if not filtro
        or filtro in clave
        or filtro in p["nombre"].lower()
        or filtro in p["software"].lower()
    ]

    if not encontrados:
        return (f"Sin paquetes que coincidan con '{software}'. "
                f"Claves disponibles: {', '.join(PAQUETES.keys())}")

    lineas = [f"PAQUETES DE LICENCIAS DSS (para {puestos} puesto(s), precios sin IVA)",
              "=" * 72]

    for clave, p in encontrados:
        m = calcular_margen(p["costo"], p["precio"], puestos)
        lineas.append(f"\n{p['nombre']}  [{clave}]")
        lineas.append(f"  {p['descripcion']}")
        lineas.append(f"  Vigencia: {p['periodicidad']}")
        lineas.append(
            f"  Costo: {_money(m['costo_total'])} | "
            f"Venta: {_money(m['precio_total'])} | "
            f"Margen: {_money(m['margen'])} ({m['margen_pct']}%)"
            + ("  << margen bajo" if m["alerta_margen"] else "")
        )

    return "\n".join(lineas)


# =============================================================
# 2. COTIZAR LICENCIAS
# =============================================================

def cotizar_licencias(paquetes, cliente_id=None, prospecto_id=None,
                      generar_pdf=True, vigencia_dias=15, notas=""):
    """
    Cotiza uno o varios paquetes de licencias.
    paquetes: lista de dicts {paquete, puestos} o lista de claves (str).

    El import de cotizador_pdf va aqui adentro a proposito (import circular).
    """
    if not paquetes:
        return "Error: indica al menos un paquete a cotizar."

    if isinstance(paquetes, str):
        paquetes = [paquetes]

    items = []
    costo_acum = 0.0
    precio_acum = 0.0
    detalle = []

    for entrada in paquetes:
        if isinstance(entrada, str):
            clave, puestos = entrada, 1
        else:
            clave = entrada.get("paquete") or entrada.get("clave") or ""
            puestos = entrada.get("puestos", 1)

        clave = (clave or "").strip().lower()
        if clave not in PAQUETES:
            return (f"Error: paquete desconocido '{clave}'. "
                    f"Claves validas: {', '.join(PAQUETES.keys())}")

        p = PAQUETES[clave]
        m = calcular_margen(p["costo"], p["precio"], puestos)

        items.append({
            "descripcion": f"{p['nombre']} - {p['descripcion']}",
            "cantidad": m["puestos"],
            "precio_unitario": float(p["precio"]),
            "costo_unitario": float(p["costo"]),
        })

        costo_acum += m["costo_total"]
        precio_acum += m["precio_total"]
        detalle.append((p["nombre"], m))

    margen = round(precio_acum - costo_acum, 2)
    margen_pct = round((margen / precio_acum) * 100, 1) if precio_acum else 0.0

    resumen = ["RESUMEN DE MARGEN", "-" * 60]
    for nombre, m in detalle:
        resumen.append(
            f"  {nombre[:38]:<38} {m['puestos']:>3}p  "
            f"{_money(m['precio_total']):>13}  {m['margen_pct']:>5}%"
        )
    resumen.append("-" * 60)
    resumen.append(f"  Costo total : {_money(costo_acum)}")
    resumen.append(f"  Venta total : {_money(precio_acum)} (sin IVA)")
    resumen.append(f"  Margen      : {_money(margen)} ({margen_pct}%)")
    if margen_pct < MARGEN_MINIMO_PCT:
        resumen.append(f"  AVISO: margen por debajo del minimo de {MARGEN_MINIMO_PCT}%")

    if not notas:
        notas = "Licencias originales adquiridas a mayorista autorizado. Incluye alta y activacion."

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
                       renovacion_auto=False, clave_activacion="", notas=""):
    """Da de alta una licencia vendida y calcula su fecha de vencimiento."""
    from tools_ventas import _sb_post

    clave = (paquete or "").strip().lower()
    if clave not in PAQUETES:
        return (f"Error: paquete desconocido '{paquete}'. "
                f"Claves validas: {', '.join(PAQUETES.keys())}")

    try:
        cid = int(cliente_id)
    except (TypeError, ValueError):
        return "Error: cliente_id debe ser un numero."

    p = PAQUETES[clave]
    m = calcular_margen(p["costo"], p["precio"], puestos)

    if fecha_inicio:
        try:
            inicio = datetime.strptime(str(fecha_inicio)[:10], "%Y-%m-%d").date()
        except ValueError:
            return "Error: fecha_inicio debe tener formato AAAA-MM-DD."
    else:
        inicio = _ahora().date()

    if p["periodicidad"] == "mensual":
        fin = inicio + timedelta(days=30)
    elif p["periodicidad"] == "anual":
        fin = inicio + timedelta(days=365)
    else:
        fin = inicio + timedelta(days=3650)

    data = {
        "cliente_id": cid,
        "paquete": clave,
        "software": p["software"],
        "edicion": p["edicion"],
        "puestos": m["puestos"],
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": fin.isoformat(),
        "periodicidad": p["periodicidad"],
        "costo_total": m["costo_total"],
        "precio_total": m["precio_total"],
        "renovacion_auto": bool(renovacion_auto),
        "estatus": "activa",
        "clave_activacion": clave_activacion,
        "notas": notas,
    }

    ok, res = _sb_post("licencias_activas", data)
    if not ok:
        return f"No se pudo registrar la licencia. {res}"

    lid = res[0]["id"] if isinstance(res, list) and res else None
    return (f"Licencia registrada (id {lid}): {p['nombre']} x{m['puestos']}\n"
            f"Vigencia: {inicio.isoformat()} a {fin.isoformat()} ({p['periodicidad']})\n"
            f"Venta: {_money(m['precio_total'])} | Margen: {_money(m['margen'])} ({m['margen_pct']}%)")


# =============================================================
# 4. RENOVACIONES PROXIMAS
# =============================================================

def obtener_renovaciones(dias=45):
    """(ok, lista) de licencias que vencen en los proximos N dias. Uso programatico."""
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
            f"{r.get('software', '')} {r.get('edicion', '') or ''} x{r.get('puestos', 1)} | "
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
            "Muestra el catalogo de paquetes de licencias de software que vende DSS "
            "(Microsoft 365, Office LTSC, Windows 11 Pro, antivirus, respaldo, Acrobat) "
            "con costo, precio de venta y margen calculado. Usala cuando pregunten que licencias "
            "hay, cuanto cuestan o cuanto se gana con ellas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "software": {"type": "string", "description": "Filtro por software o clave del paquete", "default": ""},
                "puestos": {"type": "integer", "description": "Numero de puestos o equipos para calcular el total", "default": 1}
            },
            "required": []
        }
    },
    {
        "name": "cotizar_licencias",
        "description": (
            "Cotiza uno o varios paquetes de licencias para un cliente, genera el PDF y "
            "muestra el desglose de margen. Usala cuando pidan cotizar licencias de software."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paquetes": {
                    "type": "array",
                    "description": "Paquetes a cotizar",
                    "items": {
                        "type": "object",
                        "properties": {
                            "paquete": {"type": "string", "description": "Clave del paquete (ej: m365_business_standard)"},
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
            "Registra una licencia vendida a un cliente, calcula automaticamente la fecha de "
            "vencimiento segun la periodicidad del paquete y guarda el margen. "
            "Usala cuando se cierre la venta de una licencia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {"type": "integer", "description": "ID del cliente"},
                "paquete": {"type": "string", "description": "Clave del paquete (ej: m365_business_basic)"},
                "puestos": {"type": "integer", "description": "Numero de puestos o equipos", "default": 1},
                "fecha_inicio": {"type": "string", "description": "Fecha de inicio AAAA-MM-DD (hoy si se omite)", "default": ""},
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
            "Lista las licencias que vencen en los proximos N dias, con cliente, monto y margen. "
            "Usala cuando pregunten que renovaciones vienen, que se vence o donde hay ingreso recurrente en riesgo."
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
        a.get("software", ""), a.get("puestos", 1)),
    "cotizar_licencias": lambda a: cotizar_licencias(
        a["paquetes"], a.get("cliente_id"), a.get("prospecto_id"),
        a.get("generar_pdf", True), a.get("vigencia_dias", 15), a.get("notas", "")),
    "registrar_licencia": lambda a: registrar_licencia(
        a["cliente_id"], a["paquete"], a.get("puestos", 1),
        a.get("fecha_inicio"), a.get("renovacion_auto", False),
        a.get("clave_activacion", ""), a.get("notas", "")),
    "renovaciones_proximas": lambda a: renovaciones_proximas(a.get("dias", 45)),
}


if __name__ == "__main__":
    print("=" * 55)
    print("VERIFICACION licencias.py")
    print("=" * 55)
    print(f"\nPaquetes en catalogo: {len(PAQUETES)}")
    print(f"Tools de licencias  : {len(TOOLS_LICENCIAS)}")
    print()
    print(listar_paquetes_licencias(puestos=5))
    print()
    print(renovaciones_proximas(45))
