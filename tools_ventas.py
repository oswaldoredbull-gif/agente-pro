"""
=============================================================
MODULO DE VENTAS DSS - Prospeccion, CRM, cotizador y metricas
=============================================================

Exporta:
    TOOLS_VENTAS     -> lista de tool schemas para la API de Anthropic
    FUNCIONES_VENTAS -> dict {nombre_tool: callable(args) -> str}

Depende de Supabase (tablas de schema_ventas.sql) y, opcionalmente,
de GOOGLE_PLACES_KEY para la prospeccion.

Verificacion rapida:
    venv\\Scripts\\python.exe tools_ventas.py
=============================================================
"""

import os
import requests
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv(override=True)

MEXICO_TZ = timezone(timedelta(hours=-6))

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or ""
GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_KEY") or ""

REST = f"{SUPABASE_URL}/rest/v1" if SUPABASE_URL else ""

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

IVA = 0.16
TIMEOUT = 15


# =============================================================
# HELPERS SUPABASE
# =============================================================

def _sb_listo():
    """True si hay credenciales de Supabase cargadas."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _sb_get(tabla, params=""):
    """GET contra Supabase REST. Devuelve (ok, datos_o_mensaje)."""
    if not _sb_listo():
        return False, "Supabase no configurado: falta SUPABASE_URL o SUPABASE_KEY en el .env"
    try:
        url = f"{REST}/{tabla}"
        if params:
            url += f"?{params}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return True, r.json()
        return False, f"Supabase {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"Error de conexion con Supabase: {e}"


def _sb_post(tabla, data):
    """INSERT contra Supabase REST. Devuelve (ok, datos_o_mensaje)."""
    if not _sb_listo():
        return False, "Supabase no configurado: falta SUPABASE_URL o SUPABASE_KEY en el .env"
    try:
        r = requests.post(f"{REST}/{tabla}", headers=HEADERS,
                          json=data, timeout=TIMEOUT)
        if r.status_code in (200, 201):
            return True, r.json()
        return False, f"Supabase {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"Error de conexion con Supabase: {e}"


def _sb_patch(tabla, filtro, data):
    """UPDATE contra Supabase REST. Devuelve (ok, datos_o_mensaje)."""
    if not _sb_listo():
        return False, "Supabase no configurado: falta SUPABASE_URL o SUPABASE_KEY en el .env"
    try:
        r = requests.patch(f"{REST}/{tabla}?{filtro}", headers=HEADERS,
                           json=data, timeout=TIMEOUT)
        if r.status_code in (200, 204):
            return True, (r.json() if r.text.strip() else [])
        return False, f"Supabase {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"Error de conexion con Supabase: {e}"


def _ahora():
    return datetime.now(MEXICO_TZ)


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _registrar_actividad(tipo, descripcion, prospecto_id=None, cliente_id=None):
    """Bitacora. No interrumpe el flujo si falla."""
    data = {"tipo": tipo, "descripcion": descripcion[:500]}
    if prospecto_id:
        data["prospecto_id"] = prospecto_id
    if cliente_id:
        data["cliente_id"] = cliente_id
    _sb_post("actividad", data)


# =============================================================
# 1. PROSPECTAR NEGOCIOS (Places API New)
# =============================================================
#
# Usa Places API (New): POST https://places.googleapis.com/v1/places:searchText
# La Places API vieja (maps.googleapis.com/.../textsearch/json) ya no se
# puede habilitar en proyectos de Google Cloud creados despues del
# 1 de marzo de 2025, por eso este modulo va directo a la nueva.
# La nueva ademas devuelve telefono y sitio web, que la vieja no daba.
# =============================================================

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

PLACES_CAMPOS = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.websiteUri",
])


def prospectar_negocios(giro, ciudad="Guadalajara", max_resultados=10, guardar=True):
    """Busca negocios en Google Places y opcionalmente los guarda como prospectos."""
    if not GOOGLE_PLACES_KEY:
        return ("Error: falta GOOGLE_PLACES_KEY en el .env. "
                "Consiguela en console.cloud.google.com habilitando 'Places API (New)'.")

    try:
        max_resultados = max(1, min(int(max_resultados), 20))
    except (TypeError, ValueError):
        max_resultados = 10

    consulta = f"{giro} en {ciudad}"
    try:
        r = requests.post(
            PLACES_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_PLACES_KEY,
                "X-Goog-FieldMask": PLACES_CAMPOS,
            },
            json={
                "textQuery": consulta,
                "languageCode": "es",
                "regionCode": "MX",
                "pageSize": max_resultados,
            },
            timeout=TIMEOUT,
        )
        payload = r.json()
    except Exception as e:
        return f"Error consultando Google Places: {e}"

    if r.status_code != 200:
        detalle = (payload.get("error", {}) or {}).get("message", r.text[:200])
        if r.status_code == 403:
            return (f"Google Places rechazo la llamada (403): {detalle}\n"
                    "Revisa que 'Places API (New)' este habilitada y que la key "
                    "no tenga restricciones que bloqueen este uso.")
        return f"Google Places respondio {r.status_code}: {detalle}"

    lugares = payload.get("places", [])[:max_resultados]
    if not lugares:
        return f"Sin resultados para '{consulta}'."

    lineas = [f"PROSPECCION: {consulta} ({len(lugares)} resultados)", "-" * 50]
    nuevos = 0
    repetidos = 0

    for i, lugar in enumerate(lugares, 1):
        nombre = (lugar.get("displayName") or {}).get("text") or "Sin nombre"
        direccion = lugar.get("formattedAddress", "")
        rating = lugar.get("rating")
        resenas = lugar.get("userRatingCount")
        place_id = lugar.get("id")
        telefono = lugar.get("nationalPhoneNumber", "")
        sitio = lugar.get("websiteUri", "")

        lineas.append(f"{i}. {nombre}")
        lineas.append(f"   {direccion}")
        if telefono:
            lineas.append(f"   Tel: {telefono}")
        if rating:
            lineas.append(f"   Rating: {rating} ({resenas} resenas)")
        if sitio:
            lineas.append(f"   Web: {sitio}")

        if guardar and place_id:
            ok, existente = _sb_get("prospectos", f"select=id&place_id=eq.{place_id}")
            if ok and existente:
                repetidos += 1
                lineas.append("   [ya registrado]")
                continue

            data = {
                "nombre": nombre,
                "direccion": direccion,
                "telefono": telefono,
                "ciudad": ciudad,
                "giro": giro,
                "fuente": "google_places",
                "place_id": place_id,
                "etapa": "nuevo",
            }
            if sitio:
                data["notas"] = f"Sitio web: {sitio}"
            if rating is not None:
                data["rating"] = rating
            if resenas is not None:
                data["total_resenas"] = resenas

            ok_ins, res = _sb_post("prospectos", data)
            if ok_ins:
                nuevos += 1
                lineas.append("   [guardado]")
            else:
                lineas.append(f"   [no guardado] {res}")

    if guardar:
        lineas.append("-" * 50)
        lineas.append(f"Nuevos: {nuevos} | Ya registrados: {repetidos}")
        if nuevos:
            _registrar_actividad("nota", f"Prospeccion '{consulta}': {nuevos} prospectos nuevos")

    return "\n".join(lineas)


# =============================================================
# 2. REGISTRAR PROSPECTO (alta manual)
# =============================================================

def registrar_prospecto(nombre, telefono="", direccion="", giro="",
                        ciudad="Guadalajara", valor_estimado=0, notas=""):
    """Da de alta un prospecto capturado a mano."""
    if not nombre or not nombre.strip():
        return "Error: el nombre del prospecto es obligatorio."

    try:
        valor = float(valor_estimado or 0)
    except (TypeError, ValueError):
        valor = 0.0

    data = {
        "nombre": nombre.strip(),
        "telefono": telefono,
        "direccion": direccion,
        "giro": giro,
        "ciudad": ciudad,
        "fuente": "manual",
        "etapa": "nuevo",
        "valor_estimado": valor,
        "notas": notas,
    }

    ok, res = _sb_post("prospectos", data)
    if not ok:
        return f"No se pudo registrar el prospecto. {res}"

    pid = res[0]["id"] if isinstance(res, list) and res else None
    _registrar_actividad("nota", f"Alta manual de prospecto: {nombre}", prospecto_id=pid)
    return f"Prospecto registrado (id {pid}): {nombre} | etapa: nuevo | valor estimado: {_money(valor)}"


# =============================================================
# 3. LISTAR PROSPECTOS
# =============================================================

def listar_prospectos(etapa="", ciudad="", limite=20):
    """Lista prospectos, opcionalmente filtrados por etapa y/o ciudad."""
    try:
        limite = max(1, min(int(limite), 100))
    except (TypeError, ValueError):
        limite = 20

    params = f"select=*&order=actualizado_en.desc&limit={limite}"
    if etapa:
        params += f"&etapa=eq.{etapa}"
    if ciudad:
        params += f"&ciudad=eq.{ciudad}"

    ok, datos = _sb_get("prospectos", params)
    if not ok:
        return f"No se pudieron leer los prospectos. {datos}"
    if not datos:
        return "Sin prospectos que coincidan con el filtro."

    lineas = [f"PROSPECTOS ({len(datos)})", "-" * 60]
    for p in datos:
        lineas.append(
            f"[{p['id']}] {p.get('nombre','')} | {p.get('etapa','')} | "
            f"{p.get('ciudad','')} | {p.get('telefono') or 'sin tel'} | "
            f"est. {_money(p.get('valor_estimado', 0))}"
        )
        if p.get("notas"):
            lineas.append(f"      nota: {p['notas'][:100]}")
    return "\n".join(lineas)


# =============================================================
# 4. ACTUALIZAR PROSPECTO (mover de etapa)
# =============================================================

ETAPAS = ("nuevo", "contactado", "interesado", "cotizado", "ganado", "perdido")


def actualizar_prospecto(prospecto_id, etapa="", notas="", valor_estimado=None,
                         telefono="", tipo_actividad="nota"):
    """Mueve un prospecto de etapa y/o le agrega notas. Registra la actividad."""
    try:
        pid = int(prospecto_id)
    except (TypeError, ValueError):
        return "Error: prospecto_id debe ser un numero."

    data = {"actualizado_en": _ahora().isoformat()}

    if etapa:
        if etapa not in ETAPAS:
            return f"Error: etapa invalida '{etapa}'. Validas: {', '.join(ETAPAS)}"
        data["etapa"] = etapa
    if notas:
        data["notas"] = notas
    if telefono:
        data["telefono"] = telefono
    if valor_estimado is not None:
        try:
            data["valor_estimado"] = float(valor_estimado)
        except (TypeError, ValueError):
            pass

    if len(data) == 1:
        return "Nada que actualizar: manda al menos etapa, notas, telefono o valor_estimado."

    ok, res = _sb_patch("prospectos", f"id=eq.{pid}", data)
    if not ok:
        return f"No se pudo actualizar. {res}"
    if not res:
        return f"No existe el prospecto {pid}."

    p = res[0]
    desc = f"Actualizacion de {p.get('nombre','prospecto')}"
    if etapa:
        desc += f" -> etapa {etapa}"
    if notas:
        desc += f" | {notas[:120]}"
    _registrar_actividad(tipo_actividad, desc, prospecto_id=pid)

    return (f"Prospecto {pid} actualizado: {p.get('nombre','')} | "
            f"etapa: {p.get('etapa','')} | valor: {_money(p.get('valor_estimado', 0))}")


# =============================================================
# 5. REGISTRAR CLIENTE
# =============================================================

def registrar_cliente(nombre, contacto="", email="", telefono="", rfc="",
                      direccion="", ciudad="Guadalajara",
                      condiciones_pago="contado", prospecto_id=None):
    """Convierte un prospecto en cliente o da de alta uno nuevo."""
    if not nombre or not nombre.strip():
        return "Error: el nombre del cliente es obligatorio."

    data = {
        "nombre": nombre.strip(),
        "contacto": contacto,
        "email": email,
        "telefono": telefono,
        "rfc": rfc,
        "direccion": direccion,
        "ciudad": ciudad,
        "condiciones_pago": condiciones_pago,
    }
    if prospecto_id:
        try:
            data["prospecto_id"] = int(prospecto_id)
        except (TypeError, ValueError):
            pass

    ok, res = _sb_post("clientes", data)
    if not ok:
        return f"No se pudo registrar el cliente. {res}"

    cid = res[0]["id"] if isinstance(res, list) and res else None

    if data.get("prospecto_id"):
        _sb_patch("prospectos", f"id=eq.{data['prospecto_id']}",
                  {"etapa": "ganado", "actualizado_en": _ahora().isoformat()})

    _registrar_actividad("nota", f"Alta de cliente: {nombre}", cliente_id=cid)
    return f"Cliente registrado (id {cid}): {nombre} | pago: {condiciones_pago}"


# =============================================================
# 6. BUSCAR EN EL CATALOGO DE PRODUCTOS (toners y consumibles)
# =============================================================

def buscar_productos(buscar="", tipo="toner", marca="", modelo_impresora="", limite=20):
    """Busca en el catalogo propio de DSS: toners, refacciones y servicios."""
    try:
        limite = max(1, min(int(limite), 60))
    except (TypeError, ValueError):
        limite = 20

    params = f"select=*&activo=is.true&order=nombre.asc&limit={limite}"
    if tipo:
        params += f"&tipo=eq.{tipo}"
    if marca:
        params += f"&marca=ilike.*{marca}*"
    if modelo_impresora:
        params += f"&modelo_compatible=ilike.*{modelo_impresora}*"
    if buscar:
        termino = buscar.strip().replace(",", " ")
        params += (f"&or=(nombre.ilike.*{termino}*,sku.ilike.*{termino}*,"
                   f"modelo_compatible.ilike.*{termino}*)")

    ok, datos = _sb_get("productos", params)
    if not ok:
        return f"No se pudo leer el catalogo de productos. {datos}"

    ok_t, todos = _sb_get("productos", "select=id&activo=is.true&limit=200")
    total = len(todos) if ok_t else None

    if not datos:
        filtro = buscar or modelo_impresora or marca or tipo or "todo"
        return (
            f"La busqueda de '{filtro}' no devolvio resultados en el catalogo propio.\n\n"
            f"OJO: esto NO significa que DSS no venda ese producto. El catalogo tiene "
            f"{total if total else 'varios'} productos activos.\n"
            f"Reintenta con menos palabras (ej: '85A' o 'CE285A' en vez de "
            f"'toner HP 85A negro'), o busca por modelo de impresora.\n"
            f"Si aun asi no aparece, di que no lo encontraste en el catalogo, no que no se vende."
        )

    lineas = [f"CATALOGO DSS ({len(datos)} de {total if total else '?'} productos, precios SIN IVA)",
              "=" * 76]
    for p in datos:
        costo = float(p.get("costo", 0) or 0)
        precio = float(p.get("precio", 0) or 0)
        mg = round((precio - costo) / precio * 100, 1) if precio else 0
        lineas.append(f"\n{p.get('nombre', '')}")
        lineas.append(f"  SKU: {p.get('sku')} | {p.get('marca', '')} | "
                      f"{p.get('rendimiento_paginas') or '?'} pags")
        if p.get("modelo_compatible"):
            lineas.append(f"  Compatible: {p['modelo_compatible']}")
        lineas.append(f"  Costo: {_money(costo)} | Venta: {_money(precio)} | "
                      f"Margen: {_money(precio - costo)} ({mg}%)")

    lineas.append("")
    lineas.append("Para cotizar, pasa el SKU en los items de cotizar_texto o cotizar_pdf; "
                  "el precio y el costo se toman solos del catalogo.")
    return "\n".join(lineas)


def _normalizar_item(item):
    """
    El modelo a veces manda los items como texto suelto ("TMX-HP-CE285A-V")
    en vez de objeto. Aceptamos ambas formas.
    """
    if isinstance(item, str):
        return {"sku": item.strip()}
    if isinstance(item, dict):
        return dict(item)
    return {"descripcion": str(item)}


def _resolver_sku(item):
    """
    Si el item trae 'sku', completa descripcion, precio y costo desde el catalogo.
    Devuelve (ok, item_resuelto_o_mensaje). Usada por crear_cotizacion.
    """
    item = _normalizar_item(item)
    sku = str(item.get("sku") or "").strip()
    if not sku:
        return True, item

    ok, datos = _sb_get("productos", f"select=*&sku=eq.{sku}&limit=1")
    if not ok:
        return False, f"No se pudo consultar el SKU {sku}. {datos}"
    if not datos:
        return False, (f"El SKU '{sku}' no existe en el catalogo. "
                       f"Usa buscar_productos para ver los disponibles.")

    p = datos[0]
    resuelto = dict(item)
    resuelto.setdefault("descripcion", f"{p.get('nombre')} ({p.get('sku')})")
    if not resuelto.get("descripcion"):
        resuelto["descripcion"] = f"{p.get('nombre')} ({p.get('sku')})"
    if resuelto.get("precio_unitario") in (None, "", 0):
        resuelto["precio_unitario"] = float(p.get("precio", 0) or 0)
    if resuelto.get("costo_unitario") in (None, "", 0):
        resuelto["costo_unitario"] = float(p.get("costo", 0) or 0)
    resuelto["producto_id"] = p.get("id")
    return True, resuelto


# =============================================================
# 7. COTIZAR EN TEXTO
# =============================================================

def _folio_nuevo():
    return "COT-" + _ahora().strftime("%y%m%d-%H%M%S")


def crear_cotizacion(items, cliente_id=None, prospecto_id=None,
                     vigencia_dias=15, notas=""):
    """
    Crea la cotizacion y sus items en Supabase.
    items: lista de dicts {descripcion, cantidad, precio_unitario, costo_unitario, producto_id}
    Devuelve (ok, cotizacion_dict_o_mensaje). Usada tambien por cotizador_pdf.py.
    """
    if not items:
        return False, "La cotizacion necesita al menos un item."

    # Tolerar que llegue un solo item suelto en vez de una lista.
    if isinstance(items, (str, dict)):
        items = [items]

    limpios = []
    subtotal = 0.0
    costo_total = 0.0

    for it in items:
        # Si viene con SKU, el precio y el costo salen del catalogo.
        ok_sku, it = _resolver_sku(it)
        if not ok_sku:
            return False, it

        desc = str(it.get("descripcion") or "Concepto").strip()
        if desc == "Concepto" and not it.get("sku"):
            return False, ("Cada concepto necesita un SKU del catalogo o una descripcion. "
                           "Usa buscar_productos o listar_paquetes_licencias para obtener el SKU.")
        try:
            cant = float(it.get("cantidad", 1) or 1)
        except (TypeError, ValueError):
            cant = 1.0
        try:
            precio = float(it.get("precio_unitario", 0) or 0)
        except (TypeError, ValueError):
            precio = 0.0
        try:
            costo = float(it.get("costo_unitario", 0) or 0)
        except (TypeError, ValueError):
            costo = 0.0

        importe = round(cant * precio, 2)
        subtotal += importe
        costo_total += round(cant * costo, 2)

        fila = {
            "descripcion": desc,
            "cantidad": cant,
            "precio_unitario": precio,
            "costo_unitario": costo,
            "importe": importe,
        }
        if it.get("producto_id"):
            try:
                fila["producto_id"] = int(it["producto_id"])
            except (TypeError, ValueError):
                pass
        limpios.append(fila)

    subtotal = round(subtotal, 2)
    iva = round(subtotal * IVA, 2)
    total = round(subtotal + iva, 2)

    cab = {
        "folio": _folio_nuevo(),
        "vigencia_dias": int(vigencia_dias or 15),
        "subtotal": subtotal,
        "iva": iva,
        "total": total,
        "costo_total": round(costo_total, 2),
        "estatus": "borrador",
        "notas": notas,
    }
    if cliente_id:
        try:
            cab["cliente_id"] = int(cliente_id)
        except (TypeError, ValueError):
            pass
    if prospecto_id:
        try:
            cab["prospecto_id"] = int(prospecto_id)
        except (TypeError, ValueError):
            pass

    ok, res = _sb_post("cotizaciones", cab)
    if not ok:
        return False, f"No se pudo crear la cotizacion. {res}"

    cot = res[0] if isinstance(res, list) and res else {}
    cot_id = cot.get("id")

    for fila in limpios:
        fila["cotizacion_id"] = cot_id
    ok_items, res_items = _sb_post("cotizacion_items", limpios)
    if not ok_items:
        return False, f"Cotizacion {cot_id} creada pero fallaron los items: {res_items}"

    cot["items"] = limpios
    return True, cot


def obtener_cotizacion(cotizacion_id):
    """Lee una cotizacion con sus items. Usada por cotizador_pdf.py."""
    ok, cab = _sb_get("cotizaciones", f"select=*&id=eq.{cotizacion_id}")
    if not ok:
        return False, cab
    if not cab:
        return False, f"No existe la cotizacion {cotizacion_id}."

    cot = cab[0]
    ok_it, items = _sb_get("cotizacion_items",
                           f"select=*&cotizacion_id=eq.{cotizacion_id}&order=id.asc")
    cot["items"] = items if ok_it else []

    cot["cliente"] = None
    if cot.get("cliente_id"):
        ok_c, cli = _sb_get("clientes", f"select=*&id=eq.{cot['cliente_id']}")
        if ok_c and cli:
            cot["cliente"] = cli[0]
    elif cot.get("prospecto_id"):
        ok_p, pro = _sb_get("prospectos", f"select=*&id=eq.{cot['prospecto_id']}")
        if ok_p and pro:
            cot["cliente"] = {"nombre": pro[0].get("nombre", ""),
                              "telefono": pro[0].get("telefono", ""),
                              "direccion": pro[0].get("direccion", "")}

    return True, cot


def formatear_cotizacion_texto(cot):
    """Render en texto plano de una cotizacion. Compartido con cotizador_pdf.py."""
    cliente = (cot.get("cliente") or {}).get("nombre", "Publico general")
    lineas = [
        "COTIZACION DSS - Digital Software Solutions",
        f"Folio: {cot.get('folio','')}   Fecha: {cot.get('fecha','')}",
        f"Cliente: {cliente}",
        f"Vigencia: {cot.get('vigencia_dias', 15)} dias",
        "-" * 62,
        f"{'Cant':>5}  {'Concepto':<32} {'P.Unit':>10} {'Importe':>11}",
        "-" * 62,
    ]
    for it in cot.get("items", []):
        lineas.append(
            f"{it.get('cantidad', 0):>5.0f}  {str(it.get('descripcion',''))[:32]:<32} "
            f"{float(it.get('precio_unitario', 0)):>10,.2f} {float(it.get('importe', 0)):>11,.2f}"
        )
    lineas += [
        "-" * 62,
        f"{'Subtotal:':>50} {float(cot.get('subtotal', 0)):>11,.2f}",
        f"{'IVA 16%:':>50} {float(cot.get('iva', 0)):>11,.2f}",
        f"{'TOTAL:':>50} {float(cot.get('total', 0)):>11,.2f}",
    ]
    if cot.get("notas"):
        lineas += ["", f"Notas: {cot['notas']}"]
    return "\n".join(lineas)


def cotizar_texto(items, cliente_id=None, prospecto_id=None,
                  vigencia_dias=15, notas=""):
    """Crea una cotizacion y la devuelve en texto plano (sin PDF)."""
    ok, cot = crear_cotizacion(items, cliente_id, prospecto_id, vigencia_dias, notas)
    if not ok:
        return cot

    if cot.get("cliente_id"):
        ok_c, cli = _sb_get("clientes", f"select=nombre&id=eq.{cot['cliente_id']}")
        if ok_c and cli:
            cot["cliente"] = cli[0]

    _registrar_actividad("cotizacion",
                         f"Cotizacion {cot.get('folio')} por {_money(cot.get('total', 0))}",
                         prospecto_id=cot.get("prospecto_id"),
                         cliente_id=cot.get("cliente_id"))

    if cot.get("prospecto_id"):
        _sb_patch("prospectos", f"id=eq.{cot['prospecto_id']}",
                  {"etapa": "cotizado", "actualizado_en": _ahora().isoformat()})

    margen = float(cot.get("total", 0)) - float(cot.get("iva", 0)) - float(cot.get("costo_total", 0))
    return (formatear_cotizacion_texto(cot) +
            f"\n\n(id interno: {cot.get('id')} | margen estimado: {_money(margen)})")


# =============================================================
# 7. METRICAS DE VENTAS
# =============================================================

def metricas_ventas(periodo="semana"):
    """Resumen del embudo y de las metricas de la semana."""
    salida = ["METRICAS DE VENTAS DSS", "=" * 50, ""]

    ok, embudo = _sb_get("embudo", "select=*")
    if ok and embudo:
        orden = {e: i for i, e in enumerate(ETAPAS)}
        embudo = sorted(embudo, key=lambda r: orden.get(r.get("etapa"), 99))
        salida.append("EMBUDO")
        total_p = 0
        total_v = 0.0
        for fila in embudo:
            n = int(fila.get("prospectos", 0) or 0)
            v = float(fila.get("valor_estimado", 0) or 0)
            total_p += n
            total_v += v
            salida.append(f"  {str(fila.get('etapa','')):<12} {n:>4}   {_money(v)}")
        salida.append(f"  {'TOTAL':<12} {total_p:>4}   {_money(total_v)}")
    elif ok:
        salida.append("EMBUDO: sin prospectos registrados todavia.")
    else:
        salida.append(f"EMBUDO: no disponible. {embudo}")

    salida.append("")

    ok_m, met = _sb_get("metricas_semana", "select=*")
    if ok_m and met:
        m = met[0]
        salida.append("ULTIMOS 7 DIAS")
        salida.append(f"  Prospectos nuevos:      {m.get('prospectos_nuevos', 0)}")
        salida.append(f"  Actividades:            {m.get('actividades', 0)}")
        salida.append(f"  Cotizaciones emitidas:  {m.get('cotizaciones_emitidas', 0)}")
        salida.append(f"  Monto cotizado:         {_money(m.get('monto_cotizado', 0))}")
        salida.append(f"  Cotizaciones ganadas:   {m.get('cotizaciones_ganadas', 0)}")
        salida.append(f"  Monto ganado:           {_money(m.get('monto_ganado', 0))}")
        salida.append(f"  Margen ganado:          {_money(m.get('margen_ganado', 0))}")
        salida.append(f"  Entregas realizadas:    {m.get('entregas_realizadas', 0)}")
    else:
        salida.append(f"METRICAS SEMANA: no disponible. {met}")

    return "\n".join(salida)


# =============================================================
# DEFINICION DE HERRAMIENTAS PARA CLAUDE
# =============================================================

TOOLS_VENTAS = [
    {
        "name": "prospectar_negocios",
        "description": (
            "Busca negocios reales en Google Places por giro y ciudad y los guarda como prospectos "
            "en el CRM de DSS. Usala cuando pidan buscar clientes potenciales, prospectar o "
            "encontrar negocios de un giro (ej: notarias, despachos contables, escuelas)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "giro": {"type": "string", "description": "Giro o tipo de negocio a buscar (ej: despachos contables)"},
                "ciudad": {"type": "string", "description": "Ciudad de busqueda", "default": "Guadalajara"},
                "max_resultados": {"type": "integer", "description": "Maximo de negocios (1-20)", "default": 10},
                "guardar": {"type": "boolean", "description": "Guardar los resultados como prospectos", "default": True}
            },
            "required": ["giro"]
        }
    },
    {
        "name": "registrar_prospecto",
        "description": "Da de alta manualmente un prospecto en el CRM de DSS. Usala cuando el usuario dicte los datos de un cliente potencial.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre del negocio o persona"},
                "telefono": {"type": "string", "description": "Telefono de contacto", "default": ""},
                "direccion": {"type": "string", "description": "Direccion", "default": ""},
                "giro": {"type": "string", "description": "Giro del negocio", "default": ""},
                "ciudad": {"type": "string", "description": "Ciudad", "default": "Guadalajara"},
                "valor_estimado": {"type": "number", "description": "Valor estimado del negocio en pesos", "default": 0},
                "notas": {"type": "string", "description": "Notas libres", "default": ""}
            },
            "required": ["nombre"]
        }
    },
    {
        "name": "listar_prospectos",
        "description": "Lista los prospectos del CRM de DSS, con filtro opcional por etapa (nuevo, contactado, interesado, cotizado, ganado, perdido) y por ciudad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "etapa": {"type": "string", "description": "Filtrar por etapa del embudo", "default": ""},
                "ciudad": {"type": "string", "description": "Filtrar por ciudad", "default": ""},
                "limite": {"type": "integer", "description": "Maximo de registros (1-100)", "default": 20}
            },
            "required": []
        }
    },
    {
        "name": "actualizar_prospecto",
        "description": (
            "Mueve un prospecto de etapa del embudo, le agrega notas o actualiza su valor estimado, "
            "y registra la actividad en la bitacora. Usala tras una llamada, visita o mensaje."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prospecto_id": {"type": "integer", "description": "ID del prospecto"},
                "etapa": {"type": "string", "description": "Nueva etapa: nuevo, contactado, interesado, cotizado, ganado, perdido", "default": ""},
                "notas": {"type": "string", "description": "Notas o resultado del contacto", "default": ""},
                "valor_estimado": {"type": "number", "description": "Nuevo valor estimado en pesos"},
                "telefono": {"type": "string", "description": "Telefono corregido o nuevo", "default": ""},
                "tipo_actividad": {"type": "string", "description": "Tipo de contacto: llamada, visita, correo, whatsapp, nota", "default": "nota"}
            },
            "required": ["prospecto_id"]
        }
    },
    {
        "name": "registrar_cliente",
        "description": "Da de alta un cliente de DSS. Si se pasa prospecto_id, ademas marca ese prospecto como ganado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre comercial del cliente"},
                "contacto": {"type": "string", "description": "Persona de contacto", "default": ""},
                "email": {"type": "string", "description": "Correo electronico", "default": ""},
                "telefono": {"type": "string", "description": "Telefono", "default": ""},
                "rfc": {"type": "string", "description": "RFC para facturacion", "default": ""},
                "direccion": {"type": "string", "description": "Direccion", "default": ""},
                "ciudad": {"type": "string", "description": "Ciudad", "default": "Guadalajara"},
                "condiciones_pago": {"type": "string", "description": "contado, 15 dias, 30 dias, etc.", "default": "contado"},
                "prospecto_id": {"type": "integer", "description": "ID del prospecto que se convierte en cliente"}
            },
            "required": ["nombre"]
        }
    },
    {
        "name": "buscar_productos",
        "description": (
            "Busca en el catalogo propio de DSS: toners compatibles, refacciones y servicios, "
            "con SKU, costo, precio de venta y margen. Cada toner existe en dos lineas: "
            "-E (Elite) y -V (Caja VDE), con costos distintos. "
            "USALA SIEMPRE antes de cotizar un toner: nunca inventes ni pidas precios al usuario, "
            "salen del catalogo. Puedes buscar por nombre, SKU, clave del toner (85A, CE285A) "
            "o por modelo de impresora."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "buscar": {"type": "string", "description": "Texto: nombre, SKU o clave (ej: 85A, CE285A, TN660)", "default": ""},
                "tipo": {"type": "string", "description": "toner, licencia, servicio o refaccion. Vacio para todos", "default": "toner"},
                "marca": {"type": "string", "description": "Filtrar por marca (HP, Brother, Samsung)", "default": ""},
                "modelo_impresora": {"type": "string", "description": "Modelo de impresora del cliente (ej: M404dn)", "default": ""},
                "limite": {"type": "integer", "description": "Maximo de resultados (1-60)", "default": 20}
            },
            "required": []
        }
    },
    {
        "name": "cotizar_texto",
        "description": (
            "Crea una cotizacion de DSS y la devuelve en texto plano, calculando subtotal, IVA 16% y total. "
            "Usala cuando pidan una cotizacion rapida sin PDF. Si piden el PDF, usa cotizar_pdf."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Conceptos a cotizar. Cada elemento debe ser un OBJETO, no texto suelto: {\"sku\": \"TMX-HP-CE285A-V\", \"cantidad\": 5}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku": {"type": "string", "description": "SKU del catalogo DSS. Si lo pasas, la descripcion, el precio y el costo se toman solos del catalogo y no hace falta nada mas"},
                            "descripcion": {"type": "string", "description": "Descripcion del concepto. Solo si no hay SKU"},
                            "cantidad": {"type": "number", "description": "Cantidad", "default": 1},
                            "precio_unitario": {"type": "number", "description": "Precio de venta unitario sin IVA. Solo si no hay SKU"},
                            "costo_unitario": {"type": "number", "description": "Costo unitario, para calcular margen. Solo si no hay SKU", "default": 0},
                            "producto_id": {"type": "integer", "description": "ID del producto en catalogo, si aplica"}
                        },
                        "required": []
                    }
                },
                "cliente_id": {"type": "integer", "description": "ID del cliente"},
                "prospecto_id": {"type": "integer", "description": "ID del prospecto, si aun no es cliente"},
                "vigencia_dias": {"type": "integer", "description": "Dias de vigencia", "default": 15},
                "notas": {"type": "string", "description": "Notas o condiciones", "default": ""}
            },
            "required": ["items"]
        }
    },
    {
        "name": "metricas_ventas",
        "description": "Muestra el embudo de ventas de DSS por etapa y las metricas de los ultimos 7 dias: prospectos nuevos, cotizaciones, monto cotizado, monto y margen ganados, entregas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {"type": "string", "description": "Periodo de referencia", "default": "semana"}
            },
            "required": []
        }
    },
]


FUNCIONES_VENTAS = {
    "prospectar_negocios": lambda a: prospectar_negocios(
        a["giro"], a.get("ciudad", "Guadalajara"),
        a.get("max_resultados", 10), a.get("guardar", True)),
    "registrar_prospecto": lambda a: registrar_prospecto(
        a["nombre"], a.get("telefono", ""), a.get("direccion", ""),
        a.get("giro", ""), a.get("ciudad", "Guadalajara"),
        a.get("valor_estimado", 0), a.get("notas", "")),
    "listar_prospectos": lambda a: listar_prospectos(
        a.get("etapa", ""), a.get("ciudad", ""), a.get("limite", 20)),
    "actualizar_prospecto": lambda a: actualizar_prospecto(
        a["prospecto_id"], a.get("etapa", ""), a.get("notas", ""),
        a.get("valor_estimado"), a.get("telefono", ""),
        a.get("tipo_actividad", "nota")),
    "registrar_cliente": lambda a: registrar_cliente(
        a["nombre"], a.get("contacto", ""), a.get("email", ""),
        a.get("telefono", ""), a.get("rfc", ""), a.get("direccion", ""),
        a.get("ciudad", "Guadalajara"), a.get("condiciones_pago", "contado"),
        a.get("prospecto_id")),
    "buscar_productos": lambda a: buscar_productos(
        a.get("buscar", ""), a.get("tipo", "toner"), a.get("marca", ""),
        a.get("modelo_impresora", ""), a.get("limite", 20)),
    "cotizar_texto": lambda a: cotizar_texto(
        a["items"], a.get("cliente_id"), a.get("prospecto_id"),
        a.get("vigencia_dias", 15), a.get("notas", "")),
    "metricas_ventas": lambda a: metricas_ventas(a.get("periodo", "semana")),
}


# =============================================================
# VERIFICACION (paso 1.4 del brief)
# =============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("VERIFICACION tools_ventas.py")
    print("=" * 55)

    print(f"\nSUPABASE_URL      : {'OK' if SUPABASE_URL else 'FALTA'}")
    print(f"SUPABASE_KEY      : {'OK' if SUPABASE_KEY else 'FALTA'}")
    print(f"GOOGLE_PLACES_KEY : {'OK' if GOOGLE_PLACES_KEY else 'FALTA (prospectar_negocios no funcionara)'}")

    if not _sb_listo():
        print("\nSupabase FALLO: revisa SUPABASE_URL y SUPABASE_KEY en el .env")
        raise SystemExit(1)

    faltantes = []
    for tabla in ("prospectos", "clientes", "impresoras", "productos",
                  "cotizaciones", "cotizacion_items", "contratos",
                  "entregas", "actividad"):
        ok, detalle = _sb_get(tabla, "select=id&limit=1")
        if not ok:
            faltantes.append((tabla, str(detalle)))

    for vista in ("embudo", "metricas_semana"):
        ok, detalle = _sb_get(vista, "select=*&limit=1")
        if not ok:
            faltantes.append((f"vista {vista}", str(detalle)))

    if faltantes:
        print(f"\nSupabase FALLO: {len(faltantes)} objeto(s) no se pudieron leer.\n")
        for nombre, detalle in faltantes:
            print(f"  - {nombre}: {detalle[:160]}")

        primer_error = faltantes[0][1]
        print("\nDIAGNOSTICO:")
        if "PGRST205" in primer_error or "404" in primer_error:
            print("  Las tablas no existen. Ejecuta schema_ventas.sql en el SQL Editor")
            print("  de Supabase y despues schema_licencias.sql.")
        elif "42501" in primer_error or "401" in primer_error or "permission" in primer_error.lower():
            print("  Las tablas existen pero la anon key no tiene permiso de lectura.")
            print("  Revisa RLS: en Supabase > Table Editor > cada tabla > RLS.")
            print("  Opcion rapida (solo si la base es privada):")
            print("    alter table prospectos disable row level security;")
        elif "Error de conexion" in primer_error:
            print("  No hubo respuesta de Supabase. Revisa tu conexion y que")
            print("  SUPABASE_URL apunte al proyecto correcto.")
        else:
            print("  Revisa el mensaje de arriba: viene tal cual de Supabase.")
        raise SystemExit(1)

    print("\nSupabase OK")
    print(f"Tools de ventas cargadas: {len(TOOLS_VENTAS)}")
    print()
    print(metricas_ventas())
