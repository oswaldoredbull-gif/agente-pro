"""
=============================================================
PRUEBA DE PUNTA A PUNTA - Modulo de ventas DSS
=============================================================

Ejercita las 12 tools nuevas contra Supabase real y borra al
final todo lo que haya creado.

    venv\\Scripts\\python.exe test_ventas.py

No modifica ningun archivo del proyecto.
=============================================================
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

import tools_ventas as tv
import licencias as lic
import alertas_ventas as av
from cotizador_pdf import cotizar_pdf

MARCA = "ZZ-PRUEBA-DSS"
creados = {"prospectos": [], "clientes": [], "cotizaciones": [],
           "licencias_activas": [], "actividad": []}

ok_total = 0
fallos = []


def paso(n, titulo):
    print(f"\n{'-' * 62}\n{n}. {titulo}\n{'-' * 62}")


def check(nombre, condicion, detalle=""):
    global ok_total
    if condicion:
        ok_total += 1
        print(f"   OK   {nombre}")
    else:
        fallos.append(nombre)
        print(f"   FALLA {nombre}  {detalle}")


def borrar(tabla, ids):
    if not ids:
        return
    lista = ",".join(str(i) for i in ids)
    try:
        requests.delete(f"{tv.REST}/{tabla}?id=in.({lista})",
                        headers=tv.HEADERS, timeout=15)
    except Exception as e:
        print(f"   (no se pudo limpiar {tabla}: {e})")


# =============================================================
print("=" * 62)
print("PRUEBA DE PUNTA A PUNTA - MODULO DE VENTAS DSS")
print("=" * 62)

# -------------------------------------------------------------
paso(0, "Credenciales")
print(f"   SUPABASE          : {'OK' if tv._sb_listo() else 'FALTA'}")
print(f"   GOOGLE_PLACES_KEY : {'OK' if tv.GOOGLE_PLACES_KEY else 'FALTA (se omite prospectar_negocios)'}")
print(f"   ANTHROPIC_API_KEY : {'presente' if os.getenv('ANTHROPIC_API_KEY') else 'FALTA'}")

if not tv._sb_listo():
    print("\nSin Supabase no se puede probar nada. Abortando.")
    sys.exit(1)

# -------------------------------------------------------------
paso(1, "Llamada real a la API de Anthropic (valida la key)")
try:
    from anthropic import Anthropic
    r = Anthropic().messages.create(
        model="claude-sonnet-4-6", max_tokens=8,
        messages=[{"role": "user", "content": "Responde solo: ok"}],
    )
    check("API de Anthropic responde", True)
    print(f"        respuesta: {r.content[0].text.strip()[:40]}")
except Exception as e:
    check("API de Anthropic responde", False, str(e)[:150])

# -------------------------------------------------------------
paso(2, "registrar_prospecto")
salida = tv.registrar_prospecto(
    nombre=f"{MARCA} Despacho Contable",
    telefono="3312345678", giro="despacho contable",
    ciudad="Guadalajara", valor_estimado=15000,
    notas="Alta automatica de la prueba")
print("   " + salida)
check("prospecto creado", "Prospecto registrado" in salida, salida[:120])

pid = None
ok, datos = tv._sb_get("prospectos", f"select=id&nombre=like.{MARCA}*&order=id.desc&limit=1")
if ok and datos:
    pid = datos[0]["id"]
    creados["prospectos"].append(pid)
check("id recuperado", pid is not None)

# -------------------------------------------------------------
paso(3, "listar_prospectos")
salida = tv.listar_prospectos(etapa="nuevo", limite=5)
check("lista devuelve el prospecto", MARCA in salida, salida[:120])

# -------------------------------------------------------------
paso(4, "actualizar_prospecto (mover de etapa)")
salida = tv.actualizar_prospecto(pid, etapa="interesado",
                                 notas="Le interesan toners y licencias",
                                 tipo_actividad="llamada")
print("   " + salida)
check("etapa movida a interesado", "interesado" in salida, salida[:120])

# -------------------------------------------------------------
paso(5, "registrar_cliente (convierte el prospecto)")
salida = tv.registrar_cliente(
    nombre=f"{MARCA} Despacho Contable SA",
    contacto="Contacto Prueba", email="prueba@ejemplo.com",
    telefono="3312345678", rfc="XAXX010101000",
    condiciones_pago="15 dias", prospecto_id=pid)
print("   " + salida)
check("cliente creado", "Cliente registrado" in salida, salida[:120])

cid = None
ok, datos = tv._sb_get("clientes", f"select=id&nombre=like.{MARCA}*&order=id.desc&limit=1")
if ok and datos:
    cid = datos[0]["id"]
    creados["clientes"].append(cid)
check("cliente recuperado", cid is not None)

ok, datos = tv._sb_get("prospectos", f"select=etapa&id=eq.{pid}")
check("prospecto quedo en 'ganado'",
      ok and datos and datos[0]["etapa"] == "ganado",
      str(datos)[:80] if ok else "")

# -------------------------------------------------------------
paso(6, "cotizar_texto")
salida = tv.cotizar_texto(
    items=[{"descripcion": "Toner compatible HP CF280A",
            "cantidad": 5, "precio_unitario": 320, "costo_unitario": 180}],
    cliente_id=cid, notas="Cotizacion de prueba")
print("   " + salida.replace("\n", "\n   ")[:700])
check("cotizacion en texto generada", "TOTAL" in salida, salida[:120])

ok, datos = tv._sb_get("cotizaciones", f"select=id,subtotal,iva,total&cliente_id=eq.{cid}&order=id.desc&limit=1")
if ok and datos:
    creados["cotizaciones"].append(datos[0]["id"])
    sub, iva, tot = float(datos[0]["subtotal"]), float(datos[0]["iva"]), float(datos[0]["total"])
    check("subtotal correcto (5 x 320 = 1600)", abs(sub - 1600) < 0.01, f"subtotal={sub}")
    check("IVA 16% correcto (256)", abs(iva - 256) < 0.01, f"iva={iva}")
    check("total correcto (1856)", abs(tot - 1856) < 0.01, f"total={tot}")

# -------------------------------------------------------------
paso(7, "listar_paquetes_licencias (catalogo real de CT)")
salida = lic.listar_paquetes_licencias("microsoft", puestos=5)
check("catalogo con margen", "Margen" in salida and "SKU:" in salida, salida[:150])

# Tomamos un SKU real del catalogo para las pruebas siguientes, en vez de
# uno fijo: CT cambia el catalogo y un SKU quemado envejece mal.
ok_cat, catalogo = lic.consultar_catalogo(buscar="microsoft", limite=50, usar_cache=False)
sku_prueba = None
if ok_cat and catalogo:
    con_costo = [p for p in catalogo if float(p.get("costo", 0) or 0) > 0]
    if con_costo:
        sku_prueba = con_costo[0]["sku"]
        print(f"        usando SKU real: {sku_prueba} - {str(con_costo[0].get('nombre'))[:40]}")
check("SKU real obtenido del catalogo", sku_prueba is not None,
      "no se pudo leer el catalogo de licencias")

# -------------------------------------------------------------
paso(8, "cotizar_licencias + cotizar_pdf")
salida = lic.cotizar_licencias(
    paquetes=[{"paquete": sku_prueba, "puestos": 3}],
    cliente_id=cid, generar_pdf=True, notas="Licencias de prueba") if sku_prueba else "omitido: sin SKU"
print("   " + salida.replace("\n", "\n   ")[:900])
check("PDF generado", ".pdf" in salida.lower(), salida[:150])
check("resumen de margen presente", "Margen" in salida, salida[:150])

ok, datos = tv._sb_get("cotizaciones", f"select=id,pdf_ruta&cliente_id=eq.{cid}&order=id.desc&limit=1")
if ok and datos:
    creados["cotizaciones"].append(datos[0]["id"])
    ruta = datos[0].get("pdf_ruta") or ""
    check("pdf_ruta guardada en Supabase", bool(ruta), "vacia")
    check("archivo PDF existe en disco", bool(ruta) and os.path.exists(ruta), ruta)

# -------------------------------------------------------------
paso(9, "registrar_licencia")
salida = lic.registrar_licencia(
    cliente_id=cid, paquete=sku_prueba, puestos=3,
    renovacion_auto=False, notas="Licencia de prueba") if sku_prueba else "omitido: sin SKU"
print("   " + salida.replace("\n", "\n   "))
check("licencia registrada", "Licencia registrada" in salida, salida[:120])

ok, datos = tv._sb_get("licencias_activas", f"select=id&cliente_id=eq.{cid}&order=id.desc&limit=1")
if ok and datos:
    creados["licencias_activas"].append(datos[0]["id"])
check("licencia recuperada", ok and bool(datos))

# -------------------------------------------------------------
paso(10, "renovaciones_proximas (vista renovaciones)")
salida = lic.renovaciones_proximas(400)
check("vista renovaciones responde", "RENOVACIONES" in salida or "Sin renovaciones" in salida, salida[:120])
print("   " + salida.replace("\n", "\n   ")[:400])

# -------------------------------------------------------------
paso(11, "metricas_ventas (vistas embudo y metricas_semana)")
salida = tv.metricas_ventas()
print("   " + salida.replace("\n", "\n   "))
check("embudo disponible", "no disponible" not in salida, salida[:150])

# -------------------------------------------------------------
paso(12, "prospectar_negocios (Google Places)")
if tv.GOOGLE_PLACES_KEY:
    salida = tv.prospectar_negocios("papelerias", "Zapopan", 3, guardar=False)
    print("   " + salida.replace("\n", "\n   ")[:500])
    check("Google Places responde", "PROSPECCION" in salida, salida[:150])
else:
    salida = tv.prospectar_negocios("papelerias", "Zapopan", 3, guardar=False)
    check("error controlado sin la key", "GOOGLE_PLACES_KEY" in salida, salida[:120])

# -------------------------------------------------------------
paso(13, "alertas_ventas en seco (sin enviar a Telegram)")
for job in av.JOBS:
    try:
        msg = job["func"]()
        print(f"   OK   {job['nombre']:<28} {'con contenido' if msg else 'sin novedades'}")
        ok_total += 1
    except Exception as e:
        fallos.append(f"alerta {job['nombre']}")
        print(f"   FALLA {job['nombre']:<28} {e}")

# =============================================================
paso(14, "Limpieza de datos de prueba")
ok, acts = tv._sb_get("actividad", f"select=id&prospecto_id=eq.{pid}") if pid else (False, [])
if ok:
    creados["actividad"] = [a["id"] for a in acts]

for tabla in ("licencias_activas", "cotizaciones", "actividad", "clientes", "prospectos"):
    ids = sorted(set(creados[tabla]))
    if ids:
        borrar(tabla, ids)
        print(f"   borrados {len(ids)} de {tabla}")

restan = 0
for tabla, campo in (("prospectos", "nombre"), ("clientes", "nombre")):
    ok, datos = tv._sb_get(tabla, f"select=id&{campo}=like.{MARCA}*")
    if ok:
        restan += len(datos)
check("base limpia tras la prueba", restan == 0, f"quedan {restan} registros con {MARCA}")

# =============================================================
print("\n" + "=" * 62)
if fallos:
    print(f"RESULTADO: {ok_total} OK, {len(fallos)} FALLAS")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
else:
    print(f"RESULTADO: {ok_total} verificaciones OK, 0 fallas")
    print("El modulo de ventas DSS funciona de punta a punta.")
print("=" * 62)
