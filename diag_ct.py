"""
Diagnostico del catalogo de CT Internacional.
Solo lectura: no escribe nada en la base ni toca la sincronizacion.

    venv\\Scripts\\python.exe diag_ct.py
    venv\\Scripts\\python.exe diag_ct.py "windows 11 pro"
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

SECRET = os.getenv("DSS_CATALOGO_SECRET") or ""
URL = (os.getenv("DSS_CATALOGO_URL") or "").replace("catalogo-interno", "ct-diagnostico")

if not SECRET or not URL:
    print("Faltan DSS_CATALOGO_URL o DSS_CATALOGO_SECRET en el .env")
    raise SystemExit(1)

termino = " ".join(sys.argv[1:]) or "microsoft 365"

print(f"Bajando el catalogo de CT por FTP y buscando '{termino}'...")
print("Esto tarda: son varios miles de productos.\n")

try:
    r = requests.get(URL, params={"q": termino},
                     headers={"x-dss-secret": SECRET}, timeout=180)
except Exception as e:
    print(f"Error de conexion: {e}")
    raise SystemExit(1)

if r.status_code != 200:
    print(f"La funcion respondio {r.status_code}: {r.text[:300]}")
    raise SystemExit(1)

d = r.json()
if not d.get("ok"):
    print(f"Fallo en el paso '{d.get('paso')}': {d.get('error')}")
    raise SystemExit(1)

print("=" * 78)
print("RESUMEN")
print("=" * 78)
print(f"  Productos en el catalogo de CT : {d['total_catalogo_ct']:,}")
print(f"  Pasan el filtro actual         : {d['pasan_filtro_actual']:,}")
print(f"  Pasan pero quedan SIN STOCK    : {d['pasan_pero_sin_stock']:,}  <- se apagan solos")

if d.get("ejemplos_sin_stock"):
    print("\n  Ejemplos que se apagan por no tener existencia:")
    for x in d["ejemplos_sin_stock"]:
        print(f"    {x['clave']:<14} {str(x['subcategoria'])[:26]:<26} {str(x['nombre'])[:44]}")

print("\n" + "=" * 78)
print("CATEGORIAS DEL CATALOGO DE CT")
print("=" * 78)
print(f"  {'categoria':<34}{'total':>8}{'pasan filtro':>14}")
print("  " + "-" * 56)
for c in d["categorias"][:25]:
    marca = "  <-- entra" if c["pasan_filtro"] else ""
    print(f"  {str(c['categoria'])[:34]:<34}{c['total']:>8}{c['pasan_filtro']:>14}{marca}")

print("\n" + "=" * 78)
print(f"BUSQUEDA: '{d['busqueda']}'")
print("=" * 78)
print(f"  Coincidencias en CT        : {d['coincidencias_total']}")
print(f"  De esas, FUERA del filtro  : {d['coincidencias_fuera_del_filtro']}")
print()

for x in d.get("detalle", []):
    estado = "PASA " if x["pasa_filtro_actual"] else "FUERA"
    print(f"[{estado}] {str(x['clave']):<14} {str(x['categoria'])[:12]:<12} "
          f"{str(x['subcategoria'])[:24]:<24} stock={x['stock']:<5} "
          f"${x['precio']} {x['moneda']}")
    print(f"          {str(x['descripcion'])[:88]}")
    if x.get("motivo_exclusion"):
        print(f"          motivo: {x['motivo_exclusion']}")

if not d.get("detalle"):
    print("  Sin coincidencias. Prueba con menos palabras.")

print()
print("Guardando el detalle completo en diag_ct_resultado.json")
with open("diag_ct_resultado.json", "w", encoding="utf-8") as f:
    json.dump(d, f, indent=1, ensure_ascii=False)
