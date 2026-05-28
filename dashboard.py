"""
=============================================================
🏠 DASHBOARD PERSONAL - Tu centro de comando diario
=============================================================

Se inicia automáticamente con tu computadora y muestra:
  - Tus tareas pendientes organizadas por prioridad
  - El clima actual de tu ciudad
  - Noticias del día sobre temas que te interesan
  - Tus contactos importantes
  - Chat rápido con el Agente Pro
  - Acciones rápidas con un click

EJECUCIÓN:
  streamlit run dashboard.py --server.port 8888

=============================================================
"""

import streamlit as st
import os
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

st.set_page_config(
    page_title="Mi Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
    .stApp {
        background: linear-gradient(160deg, #0a0a1a 0%, #111133 40%, #0d0d2b 100%);
    }

    .greeting {
        font-size: 32px;
        font-weight: 700;
        background: linear-gradient(135deg, #60a5fa, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 4px;
    }
    .date-text {
        font-size: 15px;
        color: #64748b;
        margin-bottom: 28px;
    }

    .dash-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 12px;
        backdrop-filter: blur(10px);
    }
    .card-header {
        font-size: 14px;
        font-weight: 500;
        color: #94a3b8;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .task-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 14px;
        border-radius: 10px;
        margin: 6px 0;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.04);
        transition: all 0.2s;
    }
    .task-item:hover { background: rgba(255,255,255,0.06); }
    .task-title { font-size: 14px; color: #e2e8f0; flex: 1; }
    .task-desc { font-size: 12px; color: #64748b; }
    .priority-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
    }
    .p-alta { background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.4); }
    .p-media { background: #f59e0b; box-shadow: 0 0 6px rgba(245,158,11,0.3); }
    .p-baja { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.3); }

    .weather-big {
        font-size: 42px;
        font-weight: 700;
        color: #e2e8f0;
        line-height: 1;
    }
    .weather-city {
        font-size: 15px;
        color: #94a3b8;
        margin-top: 4px;
    }
    .weather-detail {
        font-size: 13px;
        color: #64748b;
        margin-top: 8px;
        line-height: 1.8;
    }

    .news-item {
        padding: 12px 0;
        border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .news-item:last-child { border-bottom: none; }
    .news-title {
        font-size: 14px;
        color: #e2e8f0;
        font-weight: 500;
        margin-bottom: 4px;
    }
    .news-source {
        font-size: 12px;
        color: #64748b;
    }

    .contact-chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 24px;
        padding: 6px 14px 6px 6px;
        margin: 4px;
        font-size: 13px;
        color: #cbd5e1;
    }
    .contact-avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 500;
    }

    .quick-btn {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 14px;
        text-align: center;
        color: #94a3b8;
        font-size: 13px;
        cursor: pointer;
        transition: all 0.2s;
        margin: 4px 0;
    }
    .quick-btn:hover {
        background: rgba(255,255,255,0.08);
        color: #e2e8f0;
        border-color: rgba(96,165,250,0.3);
    }

    .chat-msg-user {
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        color: white;
        padding: 10px 16px;
        border-radius: 14px 14px 4px 14px;
        margin: 6px 0;
        font-size: 13px;
        max-width: 90%;
        margin-left: auto;
    }
    .chat-msg-agent {
        background: rgba(255,255,255,0.06);
        color: #e2e8f0;
        padding: 10px 16px;
        border-radius: 14px 14px 14px 4px;
        margin: 6px 0;
        font-size: 13px;
        max-width: 90%;
        border: 1px solid rgba(255,255,255,0.06);
        line-height: 1.6;
    }

    .stat-mini {
        text-align: center;
        padding: 12px;
    }
    .stat-mini-num {
        font-size: 28px;
        font-weight: 700;
        color: #60a5fa;
    }
    .stat-mini-label {
        font-size: 11px;
        color: #475569;
        margin-top: 2px;
    }

    .stTextInput > div > div > input {
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
        padding: 12px 16px !important;
        font-size: 14px !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: rgba(96,165,250,0.5) !important;
    }
    .stTextInput > div > div > input::placeholder { color: #475569 !important; }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# =============================================================
# BASE DE DATOS
# =============================================================

DB_PATH = r"C:\Users\omurillo\.gemini\antigravity\scratch\claude_agent\agente_datos.db"

def init_db():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS contactos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, email TEXT, telefono TEXT, notas TEXT, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS tareas (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, descripcion TEXT, estado TEXT DEFAULT 'pendiente', prioridad TEXT DEFAULT 'media', creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("SELECT COUNT(*) FROM contactos")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO contactos (nombre, email, telefono, notas) VALUES (?, ?, ?, ?)",
            [("Ana García","ana@ejemplo.com","33-1234-5678","Cliente principal"),
             ("Carlos López","carlos@ejemplo.com","81-9876-5432","Proveedor"),
             ("María Rodríguez","maria@ejemplo.com","55-5555-1234","Socia")])
    c.execute("SELECT COUNT(*) FROM tareas")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO tareas (titulo, descripcion, estado, prioridad) VALUES (?, ?, ?, ?)",
            [("Revisar propuesta","Propuesta del cliente","pendiente","alta"),
             ("Enviar reporte","Reporte mensual","pendiente","media"),
             ("Llamar a proveedor","Negociar precios","completada","baja")])
    conn.commit(); conn.close()

def get_tareas(estado=None):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    if estado:
        c.execute("SELECT id, titulo, descripcion, estado, prioridad FROM tareas WHERE estado=? ORDER BY CASE prioridad WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END", (estado,))
    else:
        c.execute("SELECT id, titulo, descripcion, estado, prioridad FROM tareas ORDER BY CASE prioridad WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END")
    rows = c.fetchall(); conn.close()
    return rows

def get_contactos():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id, nombre, email, telefono, notas FROM contactos ORDER BY nombre")
    rows = c.fetchall(); conn.close()
    return rows

def add_tarea(titulo, descripcion="", prioridad="media"):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO tareas (titulo, descripcion, prioridad) VALUES (?, ?, ?)", (titulo, descripcion, prioridad))
    conn.commit(); conn.close()

def complete_tarea(task_id):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE tareas SET estado='completada' WHERE id=?", (task_id,))
    conn.commit(); conn.close()

def add_contacto(nombre, email="", telefono="", notas=""):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO contactos (nombre, email, telefono, notas) VALUES (?, ?, ?, ?)", (nombre, email, telefono, notas))
    conn.commit(); conn.close()

init_db()


# =============================================================
# FUNCIONES DE DATOS
# =============================================================

def get_clima():
    ak = os.getenv("OPENWEATHER_API_KEY")
    if not ak:
        return {"temp": "--", "desc": "Configura OPENWEATHER_API_KEY", "city": "---", "humidity": "--", "wind": "--", "min": "--", "max": "--"}
    try:
        import requests
        r = requests.get("https://api.openweathermap.org/data/2.5/weather",
            params={"q": "Guadalajara,MX", "appid": ak, "units": "metric", "lang": "es"}, timeout=5)
        d = r.json()
        if r.status_code == 200:
            return {
                "temp": f"{d['main']['temp']:.0f}",
                "desc": d['weather'][0]['description'].capitalize(),
                "city": f"{d['name']}, {d['sys']['country']}",
                "humidity": f"{d['main']['humidity']}",
                "wind": f"{d['wind']['speed']:.1f}",
                "min": f"{d['main']['temp_min']:.0f}",
                "max": f"{d['main']['temp_max']:.0f}",
            }
    except Exception:
        pass
    return {"temp": "--", "desc": "Sin conexión", "city": "---", "humidity": "--", "wind": "--", "min": "--", "max": "--"}

def get_noticias():
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news("tecnología inteligencia artificial México", max_results=5))
        if results:
            return [{"title": r["title"], "source": r.get("source", ""), "body": r.get("body", "")[:100]} for r in results]
    except Exception:
        pass
    return [{"title": "Configura duckduckgo-search para ver noticias", "source": "pip install duckduckgo-search", "body": ""}]


# =============================================================
# CHAT CON AGENTE
# =============================================================

HERRAMIENTAS_CHAT = [
    {"name":"consultar_base_datos","description":"SQL en tablas: contactos y tareas.","input_schema":{"type":"object","properties":{"consulta_sql":{"type":"string"}},"required":["consulta_sql"]}},
]

def chat_agente(mensaje):
    try:
        client = Anthropic()
        if "chat_msgs" not in st.session_state:
            st.session_state.chat_msgs = []
        st.session_state.chat_msgs.append({"role": "user", "content": mensaje})
        if len(st.session_state.chat_msgs) > 20:
            st.session_state.chat_msgs = st.session_state.chat_msgs[-20:]

        def exec_sql(sql):
            up = sql.strip().upper()
            if any(p in up for p in ["DROP","DELETE","ALTER","TRUNCATE"]): return "No permitido."
            conn = sqlite3.connect(DB_PATH); c = conn.cursor(); c.execute(sql)
            if up.startswith("SELECT"):
                cols = [d[0] for d in c.description] if c.description else []
                rows = c.fetchall()
                if not rows: res = "Sin resultados."
                else:
                    res = f"Columnas: {', '.join(cols)}\n"
                    for r in rows: res += " | ".join(str(v) for v in r) + "\n"
            else:
                conn.commit(); res = f"OK. Filas: {c.rowcount}"
            conn.close(); return res

        msgs = list(st.session_state.chat_msgs)
        while True:
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=800,
                system="Eres un asistente rápido en español. Tienes acceso a la base de datos con tablas: contactos (id,nombre,email,telefono,notas) y tareas (id,titulo,descripcion,estado,prioridad). Respuestas cortas y útiles.",
                tools=HERRAMIENTAS_CHAT, messages=msgs)
            if resp.stop_reason == "tool_use":
                msgs.append({"role": "assistant", "content": resp.content})
                results = []
                for b in resp.content:
                    if b.type == "tool_use":
                        r = exec_sql(b.input["consulta_sql"])
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": r})
                msgs.append({"role": "user", "content": results})
            else:
                texto = "".join(b.text for b in resp.content if hasattr(b, "text"))
                st.session_state.chat_msgs.append({"role": "assistant", "content": texto})
                return texto
    except Exception as e:
        return f"Error: {str(e)}"


# =============================================================
# INTERFAZ PRINCIPAL
# =============================================================

if "chat_history_dash" not in st.session_state:
    st.session_state.chat_history_dash = []
if "chat_msgs" not in st.session_state:
    st.session_state.chat_msgs = []

# Saludo dinámico
hora = datetime.now().hour
if hora < 12:
    saludo = "Buenos días"
elif hora < 18:
    saludo = "Buenas tardes"
else:
    saludo = "Buenas noches"

dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
hoy = datetime.now()
fecha_str = f"{dias[hoy.weekday()]} {hoy.day} de {meses[hoy.month-1]} de {hoy.year}"

st.markdown(f'<div class="greeting">{saludo}, Oswaldo</div>', unsafe_allow_html=True)
st.markdown(f'<div class="date-text">{fecha_str} — {hoy.strftime("%H:%M")}</div>', unsafe_allow_html=True)

# Layout principal: 3 columnas
col_left, col_mid, col_right = st.columns([1.2, 1, 1])

# === COLUMNA IZQUIERDA: TAREAS ===
with col_left:
    # Stats rápidos
    tareas_pendientes = get_tareas("pendiente")
    tareas_completadas = get_tareas("completada")
    contactos = get_contactos()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="stat-mini"><div class="stat-mini-num">{len(tareas_pendientes)}</div><div class="stat-mini-label">Pendientes</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-mini"><div class="stat-mini-num" style="color:#34d399">{len(tareas_completadas)}</div><div class="stat-mini-label">Completadas</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="stat-mini"><div class="stat-mini-num" style="color:#a78bfa">{len(contactos)}</div><div class="stat-mini-label">Contactos</div></div>', unsafe_allow_html=True)

    # Tareas pendientes
    st.markdown('<div class="dash-card"><div class="card-header">📋 Tareas pendientes</div>', unsafe_allow_html=True)

    if tareas_pendientes:
        for t in tareas_pendientes:
            tid, titulo, desc, estado, prio = t
            dot_class = f"p-{prio}"
            col_task, col_btn = st.columns([5, 1])
            with col_task:
                st.markdown(
                    f'<div class="task-item">'
                    f'<div class="priority-dot {dot_class}"></div>'
                    f'<div><div class="task-title">{titulo}</div>'
                    f'<div class="task-desc">{desc or ""}</div></div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            with col_btn:
                if st.button("✓", key=f"done_{tid}", help="Completar"):
                    complete_tarea(tid)
                    st.rerun()
    else:
        st.markdown('<div style="color:#64748b;font-size:14px;padding:8px">🎉 No tienes tareas pendientes</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # Agregar tarea rápida
    st.markdown('<div class="dash-card"><div class="card-header">➕ Agregar tarea</div>', unsafe_allow_html=True)
    with st.form("add_task", clear_on_submit=True):
        task_title = st.text_input("Título", placeholder="Ej: Revisar propuesta", label_visibility="collapsed")
        tc1, tc2 = st.columns(2)
        with tc1:
            task_prio = st.selectbox("Prioridad", ["alta", "media", "baja"], index=1, label_visibility="collapsed")
        with tc2:
            submitted = st.form_submit_button("Agregar", use_container_width=True)
        if submitted and task_title:
            add_tarea(task_title, prioridad=task_prio)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# === COLUMNA CENTRAL: CLIMA + NOTICIAS ===
with col_mid:
    # Clima
    st.markdown('<div class="dash-card"><div class="card-header">🌤️ Clima ahora</div>', unsafe_allow_html=True)
    with st.spinner("Cargando clima..."):
        clima = get_clima()
    st.markdown(
        f'<div class="weather-big">{clima["temp"]}°C</div>'
        f'<div class="weather-city">{clima["city"]}</div>'
        f'<div class="weather-detail">'
        f'☁️ {clima["desc"]}<br>'
        f'📊 Mín {clima["min"]}° / Máx {clima["max"]}°<br>'
        f'💧 Humedad: {clima["humidity"]}%<br>'
        f'💨 Viento: {clima["wind"]} m/s'
        f'</div>',
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Noticias
    st.markdown('<div class="dash-card"><div class="card-header">📰 Noticias del día</div>', unsafe_allow_html=True)
    with st.spinner("Cargando noticias..."):
        noticias = get_noticias()
    for n in noticias[:4]:
        st.markdown(
            f'<div class="news-item">'
            f'<div class="news-title">{n["title"][:80]}</div>'
            f'<div class="news-source">{n["source"]}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    st.markdown('</div>', unsafe_allow_html=True)


# === COLUMNA DERECHA: CONTACTOS + CHAT ===
with col_right:
    # Contactos
    st.markdown('<div class="dash-card"><div class="card-header">👥 Contactos</div>', unsafe_allow_html=True)

    colores_avatar = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626", "#0891b2"]
    for i, c in enumerate(contactos):
        cid, nombre, email, tel, notas = c
        iniciales = "".join([p[0].upper() for p in nombre.split()[:2]])
        color = colores_avatar[i % len(colores_avatar)]
        st.markdown(
            f'<div class="contact-chip">'
            f'<div class="contact-avatar" style="background:{color}22;color:{color}">{iniciales}</div>'
            f'{nombre}'
            f'</div>',
            unsafe_allow_html=True
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # Agregar contacto
    st.markdown('<div class="dash-card"><div class="card-header">➕ Agregar contacto</div>', unsafe_allow_html=True)
    with st.form("add_contact", clear_on_submit=True):
        ct_name = st.text_input("Nombre", placeholder="Juan Pérez", label_visibility="collapsed")
        ct_email = st.text_input("Email", placeholder="juan@email.com", label_visibility="collapsed")
        ct_phone = st.text_input("Teléfono", placeholder="33-1111-2222", label_visibility="collapsed")
        ct_submit = st.form_submit_button("Agregar", use_container_width=True)
        if ct_submit and ct_name:
            add_contacto(ct_name, ct_email, ct_phone)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # Chat rápido
    st.markdown('<div class="dash-card"><div class="card-header">💬 Chat rápido</div>', unsafe_allow_html=True)

    for msg in st.session_state.chat_history_dash[-6:]:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-msg-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-msg-agent">{msg["content"]}</div>', unsafe_allow_html=True)

    chat_input = st.chat_input("Pregúntale algo al agente...", key="dash_chat")
    if chat_input:
        st.session_state.chat_history_dash.append({"role": "user", "content": chat_input})
        with st.spinner("🤖"):
            resp = chat_agente(chat_input)
        st.session_state.chat_history_dash.append({"role": "assistant", "content": resp})
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# Acciones rápidas en la parte inferior
st.markdown("---")
st.markdown('<div style="font-size:12px;color:#475569;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Acciones rápidas</div>', unsafe_allow_html=True)

qc1, qc2, qc3, qc4 = st.columns(4)
with qc1:
    if st.button("🔍 Abrir Agente Pro", use_container_width=True):
        st.markdown('<script>window.open("http://localhost:8510","_blank")</script>', unsafe_allow_html=True)
with qc2:
    if st.button("🤖 Abrir Multi-Agente", use_container_width=True):
        st.markdown('<script>window.open("http://localhost:8520","_blank")</script>', unsafe_allow_html=True)
with qc3:
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.rerun()
with qc4:
    if st.button("🗑️ Limpiar chat", use_container_width=True):
        st.session_state.chat_history_dash = []
        st.session_state.chat_msgs = []
        st.rerun()

st.markdown('<div style="text-align:center;font-size:11px;color:#1e293b;margin-top:16px">Dashboard Personal — by Oswaldo Murillo</div>', unsafe_allow_html=True)
