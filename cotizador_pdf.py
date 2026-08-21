"""
=============================================================
COTIZADOR PDF - Digital Software Solutions (DSS)
=============================================================

Genera cotizaciones en PDF con reportlab y las guarda en .\\cotizaciones\\

Exporta:
    TOOL_COTIZADOR_PDF -> tool schema para la API de Anthropic
    cotizar_pdf        -> callable(args) via FUNCIONES

IMPORTANTE (regla del brief):
    La importacion de tools_ventas ocurre DENTRO de cotizar_pdf,
    nunca a nivel de modulo, para evitar el import circular
    tools_ventas -> licencias -> cotizador_pdf -> tools_ventas.

Verificacion rapida:
    venv\\Scripts\\python.exe cotizador_pdf.py
=============================================================
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer)

load_dotenv(override=True)

MEXICO_TZ = timezone(timedelta(hours=-6))
CARPETA_PDF = Path("cotizaciones")

EMPRESA = {
    "nombre": "Digital Software Solutions (DSS Toner MX)",
    "sitio": "dsstonermx.com",
    "email": os.getenv("DSS_EMAIL", "ventas@dsstonermx.com"),
    "whatsapp": os.getenv("DSS_WHATSAPP", "33 2804 8295"),
    "ciudad": "Guadalajara, Jalisco",
}

VIOLETA = colors.HexColor("#6C4AB6")
VIOLETA_SUAVE = colors.HexColor("#EDE7F6")
GRIS = colors.HexColor("#5A5A5A")


def _ahora():
    return datetime.now(MEXICO_TZ)


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


# =============================================================
# CONSTRUCCION DEL PDF (sin dependencias de Supabase)
# =============================================================

def construir_pdf(cot, ruta_salida=None):
    """
    Construye el PDF a partir de un dict de cotizacion.
    cot: {folio, fecha, vigencia_dias, cliente:{...}, items:[...],
          subtotal, iva, total, notas}
    Devuelve la ruta del archivo generado.
    """
    CARPETA_PDF.mkdir(parents=True, exist_ok=True)

    folio = cot.get("folio") or ("COT-" + _ahora().strftime("%y%m%d-%H%M%S"))
    if ruta_salida:
        ruta = Path(ruta_salida)
        ruta.parent.mkdir(parents=True, exist_ok=True)
    else:
        ruta = CARPETA_PDF / f"{folio}.pdf"

    estilos = getSampleStyleSheet()
    st_titulo = ParagraphStyle("t", parent=estilos["Title"],
                               fontSize=18, textColor=VIOLETA, spaceAfter=2)
    st_sub = ParagraphStyle("s", parent=estilos["Normal"],
                            fontSize=9, textColor=GRIS)
    st_normal = ParagraphStyle("n", parent=estilos["Normal"], fontSize=9.5)
    st_pie = ParagraphStyle("p", parent=estilos["Normal"],
                            fontSize=8, textColor=GRIS)

    doc = SimpleDocTemplate(
        str(ruta), pagesize=letter,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Cotizacion {folio}", author=EMPRESA["nombre"],
    )

    elementos = []

    # --- Encabezado ---
    elementos.append(Paragraph(EMPRESA["nombre"], st_titulo))
    elementos.append(Paragraph(
        f"{EMPRESA['ciudad']} &nbsp;|&nbsp; {EMPRESA['sitio']} &nbsp;|&nbsp; "
        f"{EMPRESA['email']} &nbsp;|&nbsp; WhatsApp {EMPRESA['whatsapp']}", st_sub))
    elementos.append(Spacer(1, 8 * mm))

    # --- Datos de la cotizacion ---
    cliente = cot.get("cliente") or {}
    fecha = cot.get("fecha") or _ahora().strftime("%Y-%m-%d")
    vigencia = cot.get("vigencia_dias", 15)

    cab = [
        ["COTIZACION", folio],
        ["Fecha", str(fecha)],
        ["Vigencia", f"{vigencia} dias"],
        ["Cliente", cliente.get("nombre", "Publico general")],
    ]
    if cliente.get("contacto"):
        cab.append(["Atencion", cliente["contacto"]])
    if cliente.get("rfc"):
        cab.append(["RFC", cliente["rfc"]])
    if cliente.get("telefono"):
        cab.append(["Telefono", cliente["telefono"]])

    t_cab = Table(cab, colWidths=[32 * mm, 140 * mm])
    t_cab.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), VIOLETA),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    elementos.append(t_cab)
    elementos.append(Spacer(1, 6 * mm))

    # --- Tabla de conceptos ---
    filas = [["Cant.", "Concepto", "P. Unitario", "Importe"]]
    for it in cot.get("items", []):
        filas.append([
            f"{float(it.get('cantidad', 1)):g}",
            Paragraph(str(it.get("descripcion", "")), st_normal),
            _money(it.get("precio_unitario", 0)),
            _money(it.get("importe",
                          float(it.get("cantidad", 1) or 1) *
                          float(it.get("precio_unitario", 0) or 0))),
        ])

    t_items = Table(filas, colWidths=[16 * mm, 106 * mm, 25 * mm, 25 * mm],
                    repeatRows=1)
    t_items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VIOLETA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, VIOLETA_SUAVE]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5CCE8")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t_items)
    elementos.append(Spacer(1, 4 * mm))

    # --- Totales ---
    tot = [
        ["Subtotal", _money(cot.get("subtotal", 0))],
        ["IVA 16%", _money(cot.get("iva", 0))],
        ["TOTAL", _money(cot.get("total", 0))],
    ]
    t_tot = Table(tot, colWidths=[147 * mm, 25 * mm], hAlign="RIGHT")
    t_tot.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), VIOLETA),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, VIOLETA),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elementos.append(t_tot)

    # --- Notas y pie ---
    if cot.get("notas"):
        elementos.append(Spacer(1, 6 * mm))
        elementos.append(Paragraph(f"<b>Notas:</b> {cot['notas']}", st_normal))

    elementos.append(Spacer(1, 10 * mm))
    elementos.append(Paragraph(
        "Precios en pesos mexicanos (MXN). Sujetos a existencias. "
        f"Cotizacion valida por {vigencia} dias a partir de la fecha de emision.<br/>"
        "Formas de pago: transferencia SPEI o tarjeta. Facturacion CFDI 4.0 disponible.",
        st_pie))

    doc.build(elementos)
    return str(ruta)


# =============================================================
# TOOL: cotizar_pdf
# =============================================================

def cotizar_pdf(items=None, cotizacion_id=None, cliente_id=None,
                prospecto_id=None, vigencia_dias=15, notas=""):
    """
    Genera el PDF de una cotizacion.

    - Si se pasa cotizacion_id, lee la cotizacion existente de Supabase.
    - Si se pasan items, crea primero la cotizacion y luego genera el PDF.

    El import de tools_ventas va aqui adentro a proposito (import circular).
    """
    from tools_ventas import (crear_cotizacion, obtener_cotizacion,
                              _sb_patch, _registrar_actividad)

    if cotizacion_id:
        ok, cot = obtener_cotizacion(cotizacion_id)
        if not ok:
            return f"No se pudo leer la cotizacion. {cot}"
    elif items:
        ok, cot = crear_cotizacion(items, cliente_id, prospecto_id,
                                   vigencia_dias, notas)
        if not ok:
            return cot
        ok2, completa = obtener_cotizacion(cot.get("id"))
        if ok2:
            cot = completa
    else:
        return "Error: manda 'items' para crear una cotizacion nueva, o 'cotizacion_id' para una existente."

    try:
        ruta = construir_pdf(cot)
    except Exception as e:
        return f"Error generando el PDF: {e}"

    ruta_abs = str(Path(ruta).resolve())

    if cot.get("id"):
        _sb_patch("cotizaciones", f"id=eq.{cot['id']}", {"pdf_ruta": ruta_abs})
        _registrar_actividad(
            "cotizacion",
            f"PDF generado para {cot.get('folio')} por {_money(cot.get('total', 0))}",
            prospecto_id=cot.get("prospecto_id"),
            cliente_id=cot.get("cliente_id"),
        )

    margen = (float(cot.get("total", 0)) - float(cot.get("iva", 0))
              - float(cot.get("costo_total", 0)))

    return (f"Cotizacion {cot.get('folio')} lista.\n"
            f"PDF: {ruta_abs}\n"
            f"Total: {_money(cot.get('total', 0))} (IVA incluido) | "
            f"Margen estimado: {_money(margen)}")


TOOL_COTIZADOR_PDF = {
    "name": "cotizar_pdf",
    "description": (
        "Genera una cotizacion de DSS en PDF con formato profesional y la guarda en la carpeta "
        "'cotizaciones'. Usala cuando pidan una cotizacion formal, un PDF o algo para enviar al cliente. "
        "Puede crear una cotizacion nueva a partir de 'items' o regenerar el PDF de una existente con 'cotizacion_id'. "
        "Para productos del catalogo pasa solo el SKU en cada item: el precio y el costo se toman del catalogo, nunca los inventes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "Conceptos a cotizar. Cada elemento debe ser un OBJETO, no texto suelto: {\"sku\": \"TMX-HP-CE285A-V\", \"cantidad\": 5}. Omitir si se usa cotizacion_id.",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "description": "SKU del catalogo DSS. Si lo pasas, descripcion, precio y costo salen solos del catalogo"},
                        "descripcion": {"type": "string", "description": "Descripcion del concepto. Solo si no hay SKU"},
                        "cantidad": {"type": "number", "description": "Cantidad", "default": 1},
                        "precio_unitario": {"type": "number", "description": "Precio de venta unitario sin IVA. Solo si no hay SKU"},
                        "costo_unitario": {"type": "number", "description": "Costo unitario, para calcular margen. Solo si no hay SKU", "default": 0},
                        "producto_id": {"type": "integer", "description": "ID del producto en catalogo, si aplica"}
                    },
                    "required": []
                }
            },
            "cotizacion_id": {"type": "integer", "description": "ID de una cotizacion ya existente"},
            "cliente_id": {"type": "integer", "description": "ID del cliente"},
            "prospecto_id": {"type": "integer", "description": "ID del prospecto, si aun no es cliente"},
            "vigencia_dias": {"type": "integer", "description": "Dias de vigencia", "default": 15},
            "notas": {"type": "string", "description": "Notas o condiciones comerciales", "default": ""}
        },
        "required": []
    }
}


# =============================================================
# VERIFICACION (paso 1.4 del brief)
# =============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("VERIFICACION cotizador_pdf.py")
    print("=" * 55)

    demo = {
        "folio": "COT-DEMO",
        "fecha": _ahora().strftime("%Y-%m-%d"),
        "vigencia_dias": 15,
        "cliente": {"nombre": "Cliente de prueba", "contacto": "Oswaldo",
                    "telefono": EMPRESA["whatsapp"]},
        "items": [
            {"descripcion": "Toner compatible HP CF280A negro (2,700 pags.)",
             "cantidad": 5, "precio_unitario": 320.00, "importe": 1600.00},
            {"descripcion": "Toner compatible Brother TN-660 negro (2,600 pags.)",
             "cantidad": 3, "precio_unitario": 295.00, "importe": 885.00},
            {"descripcion": "Servicio de mantenimiento preventivo por equipo",
             "cantidad": 2, "precio_unitario": 450.00, "importe": 900.00},
        ],
        "notas": "PDF de prueba generado por la verificacion de la Fase 1.",
    }
    demo["subtotal"] = round(sum(i["importe"] for i in demo["items"]), 2)
    demo["iva"] = round(demo["subtotal"] * 0.16, 2)
    demo["total"] = round(demo["subtotal"] + demo["iva"], 2)

    ruta = construir_pdf(demo)
    print(f"\nPDF generado: {Path(ruta).resolve()}")
    print(f"Subtotal: {_money(demo['subtotal'])} | IVA: {_money(demo['iva'])} | Total: {_money(demo['total'])}")
    print("\nreportlab OK")
