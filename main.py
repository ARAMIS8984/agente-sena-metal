import os
import json
import logging
import requests
import io
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Estado de cada usuario
estados = {}

PROGRAMAS = {
    "MEI": "Mantenimiento Electromecánico Industrial",
    "MMI": "Mecánica de Maquinaria Industrial",
    "GPI": "Gestión de la Producción Industrial",
    "CNC": "Producción de Componentes Mecánicos con Máquinas de Control Numérico Computarizado"
}

INSTRUCTORES = ["Carlos Charris", "Carlos Sabalza", "Wilfrido Romero", "Ana Maria Barrios", "Aramis Vitola", "Omar Pardey"]

FALTAS_DISCIPLINARIAS = [
    "Inasistencias injustificadas",
    "Uso de celular en ambiente",
    "No porta EPP requerido",
    "Conflicto con compañeros",
    "Abandono del ambiente sin permiso",
    "Presentación personal inadecuada",
    "Irrespeto al instructor",
    "Consumo de sustancias",
    "Otra falta disciplinaria"
]

FALTAS_ACADEMICAS = [
    "No entrega de evidencias",
    "Bajo rendimiento académico",
    "No presenta pruebas de conocimiento",
    "Incumplimiento de compromisos formativos",
    "No realiza actividades asignadas",
    "Otra falta académica"
]

MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]

SYSTEM_ANALISIS = """Eres el Asistente SENA Metalmecánica del Centro Nacional Colombo Alemán, Barranquilla. Eres como un colega experimentado que ayuda a los instructores.

Cuando recibes una novedad, analizas la situación de forma natural y humana. Respondes con este formato:

---
🎓 *ANÁLISIS DE NOVEDAD*
*Aprendiz:* [nombre]
*Ficha:* [codigo o no especificada]

📋 *SITUACIÓN:*
[Análisis breve y humano de la situación. Si has visto casos similares antes, menciona UNO de forma natural y discreta, sin nombres ni detalles.]

⚖️ *NORMA APLICABLE:*
[Artículo del Acuerdo 0009 de 2024 con mayor peso argumentativo. Si aplican varios, menciona el principal y los de refuerzo.]

✅ *PROCEDIMIENTO RECOMENDADO:*
1. [Paso inmediato]
2. [Paso siguiente]
3. [Documentación]

💡 *MI SUGERENCIA:*
[Tipo de documento recomendado con argumento breve]
---

REGLAS DEL ACUERDO 0009 DE 2024 (por peso argumentativo):

MÁXIMO PESO — Causales de cancelación:
- Art. 19: Reincidencia en faltas graves → causal de cancelación de matrícula
- Art. 20: Consumo de sustancias psicoactivas → retiro inmediato y cancelación

PESO ALTO — Obligaciones del aprendiz:
- Art. 8 lit. a: Cumplir el reglamento y normas del centro
- Art. 8 lit. c: Presentarse en condiciones físicas y mentales aptas
- Art. 8 lit. d: Asistir puntualmente a todas las actividades de formación
- Art. 8 lit. f: Mantener comportamiento respetuoso con la comunidad educativa
- Art. 15: Asistencia mínima obligatoria del 80%

PESO MEDIO — Faltas y sanciones:
- Art. 16: 3+ ausencias injustificadas → Primer Llamado de Atención
- Art. 17: 5+ ausencias injustificadas → Segundo Llamado + Plan de Mejoramiento
- Art. 22: Nota mínima aprobatoria 3.0 sobre 5.0
- Art. 23: Nota menor a 3.0 → Plan de Mejoramiento obligatorio
- Art. 28: Mínimo 60% de evidencias por competencia
- Art. 29: Menos del 60% evidencias → Plan de Mejoramiento

PESO REFERENCIAL — Convivencia:
- Art. 12 lit. f: Conductas que afecten la convivencia del ambiente

Cuando no sea clara la falta, busca el artículo de mayor peso que aplique al contexto.
Responde en español. Sé directo, profesional y humano. Máximo 200 palabras en el análisis."""

def get_estado(chat_id):
    if chat_id not in estados:
        estados[chat_id] = {"modo": "menu"}
    return estados[chat_id]

def set_estado(chat_id, datos):
    estados[chat_id] = datos

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=30)
        if r.status_code != 200:
            payload2 = {"chat_id": chat_id, "text": text.replace("*","").replace("_","").replace("`","")}
            if reply_markup:
                payload2["reply_markup"] = json.dumps(reply_markup)
            requests.post(f"{TELEGRAM_API}/sendMessage", json=payload2, timeout=30)
    except Exception as e:
        logger.error(f"Error send: {e}")

def send_document(chat_id, pdf_bytes, filename, caption=""):
    try:
        r = requests.post(
            f"{TELEGRAM_API}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, pdf_bytes, "application/pdf")},
            timeout=60
        )
        logger.info(f"Send doc: {r.status_code}")
    except Exception as e:
        logger.error(f"Error send doc: {e}")

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except: pass

def answer_callback(callback_id):
    try:
        requests.post(f"{TELEGRAM_API}/answerCallbackQuery", json={"callback_query_id": callback_id}, timeout=10)
    except: pass

def menu_principal(chat_id):
    set_estado(chat_id, {"modo": "menu"})
    send_message(chat_id,
        "👋 Bienvenido al *Agente SENA Metalmecánica*\n\n¿Qué deseas hacer?",
        reply_markup={"inline_keyboard": [
            [{"text": "📊 Seguimiento a la Formación", "callback_data": "menu_seguimiento"}],
            [{"text": "📋 Llamado de Atención", "callback_data": "llamado_inicio"}],
            [{"text": "📖 Consultar Reglamento", "callback_data": "menu_reglamento"}],
            [{"text": "📝 Generar Plan Concertado", "callback_data": "menu_plan"}]
        ]}
    )

def consultar_groq(mensajes, system):
    try:
        messages = [{"role": "system", "content": system}] + mensajes
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": messages, "max_tokens": 800, "temperature": 0.2},
            timeout=30
        )
        data = r.json()
        if r.status_code != 200:
            logger.error(f"Groq error: {data}")
            return None
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Groq exception: {e}")
        return None

# ─── FLUJO LLAMADO DE ATENCIÓN ───────────────────────────────────────────────

def llamado_paso1_aprendiz(chat_id):
    set_estado(chat_id, {"modo": "llamado", "paso": "aprendiz"})
    send_message(chat_id,
        "📋 *Llamado de Atención*\n\n*Paso 1 de 6*\n\n"
        "¿Cuál es el *nombre completo* del aprendiz?"
    )

def llamado_paso2_formacion(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "programa"
    set_estado(chat_id, estado)
    send_message(chat_id,
        f"✅ Aprendiz: *{estado['aprendiz']}*\n\n"
        "*Paso 2 de 6 — Programa de formación*\n\n"
        "¿A qué programa pertenece?",
        reply_markup={"inline_keyboard": [
            [{"text": "⚙️ CNC — Máquinas CNC", "callback_data": "prog_CNC"}],
            [{"text": "🔧 MEI — Electromecánico Industrial", "callback_data": "prog_MEI"}],
            [{"text": "🏭 MMI — Maquinaria Industrial", "callback_data": "prog_MMI"}],
            [{"text": "📊 GPI — Gestión Producción", "callback_data": "prog_GPI"}]
        ]}
    )

def llamado_paso3_ficha_instructor(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "ficha"
    set_estado(chat_id, estado)
    send_message(chat_id,
        f"✅ Programa: *{PROGRAMAS[estado['programa']]}*\n\n"
        "*Paso 3 de 6 — Ficha e instructor*\n\n"
        "Escribe el *número de ficha* del grupo:"
    )

def llamado_paso3b_instructor(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "instructor"
    set_estado(chat_id, estado)
    send_message(chat_id,
        f"✅ Ficha: *{estado['ficha']}*\n\n"
        "*¿Qué instructor(es) reportan la falta?*",
        reply_markup={"inline_keyboard": [
            [{"text": "Carlos Charris", "callback_data": "inst_Carlos Charris"}],
            [{"text": "Carlos Sabalza", "callback_data": "inst_Carlos Sabalza"}],
            [{"text": "Wilfrido Romero", "callback_data": "inst_Wilfrido Romero"}],
            [{"text": "Ana Maria Barrios", "callback_data": "inst_Ana Maria Barrios"}],
            [{"text": "Aramis Vitola", "callback_data": "inst_Aramis Vitola"}],
            [{"text": "Omar Pardey", "callback_data": "inst_Omar Pardey"}]
        ]}
    )

def llamado_paso4_tipo(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "tipo"
    set_estado(chat_id, estado)
    send_message(chat_id,
        f"✅ Instructor: *{estado['instructor']}*\n\n"
        "*Paso 4 de 6 — Tipo de llamado*",
        reply_markup={"inline_keyboard": [
            [{"text": "🛡️ Disciplinario", "callback_data": "tipo_disciplinario"}],
            [{"text": "📚 Académico", "callback_data": "tipo_academico"}]
        ]}
    )

def llamado_paso5_numero(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "numero"
    set_estado(chat_id, estado)
    send_message(chat_id,
        f"✅ Tipo: *{estado['tipo_llamado'].capitalize()}*\n\n"
        "*Paso 5 de 6 — Número de llamado*",
        reply_markup={"inline_keyboard": [
            [{"text": "1️⃣ Primer Llamado", "callback_data": "num_primero"}],
            [{"text": "2️⃣ Segundo Llamado", "callback_data": "num_segundo"}]
        ]}
    )

def llamado_paso6_falta(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "falta"
    set_estado(chat_id, estado)
    
    if estado["tipo_llamado"] == "disciplinario":
        faltas = FALTAS_DISCIPLINARIAS
    else:
        faltas = FALTAS_ACADEMICAS
    
    botones = [[{"text": f, "callback_data": f"falta_{i}"}] for i, f in enumerate(faltas)]
    
    send_message(chat_id,
        f"✅ {estado['numero_llamado'].capitalize()} Llamado *{estado['tipo_llamado'].capitalize()}*\n\n"
        "*Paso 6 de 6 — Tipo de falta*\n\n"
        "¿Cuál es la falta cometida?",
        reply_markup={"inline_keyboard": botones}
    )

def llamado_paso7_detalles(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "detalles"
    set_estado(chat_id, estado)
    
    falta = estado["falta"]
    
    if "inasistencia" in falta.lower() or "ausencia" in falta.lower():
        estado["paso"] = "mes_falta"
        set_estado(chat_id, estado)
        botones = [[{"text": m.capitalize(), "callback_data": f"mes_{m}"}] for m in MESES]
        send_message(chat_id,
            f"✅ Falta: *{falta}*\n\n"
            "¿En qué mes se registraron las inasistencias?",
            reply_markup={"inline_keyboard": botones}
        )
    else:
        send_message(chat_id,
            f"✅ Falta: *{falta}*\n\n"
            "Describe brevemente la situación:\n\n"
            "_Ejemplo: El aprendiz llegó sin el EPP el día 15 de junio de 2026_"
        )

def llamado_dias_inasistencia(chat_id):
    estado = get_estado(chat_id)
    estado["paso"] = "dias_falta"
    set_estado(chat_id, estado)
    send_message(chat_id,
        f"✅ Mes: *{estado['mes_falta'].capitalize()}*\n\n"
        "Escribe los *días de inasistencia* separados por comas:\n\n"
        "_Ejemplo: 3, 10, 15, 22_"
    )

def llamado_generar_pdf(chat_id):
    estado = get_estado(chat_id)
    send_typing(chat_id)
    send_message(chat_id, "⏳ Generando el Llamado de Atención...")
    
    try:
        pdf_bytes = generar_pdf_llamado(estado)
        
        aprendiz = estado.get("aprendiz", "Aprendiz")
        apellido = aprendiz.split()[-1]
        fecha = datetime.now().strftime("%Y%m%d")
        numero = estado.get("numero_llamado", "primer")
        tipo = estado.get("tipo_llamado", "disciplinario")
        filename = f"Llamado_{numero.capitalize()}_{tipo.capitalize()}_{apellido}_{fecha}.pdf"
        
        send_document(chat_id, pdf_bytes, filename,
            f"📄 {numero.capitalize()} Llamado de Atención {tipo.capitalize()}\n"
            f"Aprendiz: {aprendiz}"
        )
        
        send_message(chat_id,
            "✅ *Documento generado exitosamente*\n\n"
            "Recuerda:\n"
            "• Imprimir y hacer firmar al aprendiz\n"
            "• Archivar en la carpeta del aprendiz\n"
            "• Notificar a coordinación académica",
            reply_markup={"inline_keyboard": [
                [{"text": "📋 Nuevo llamado", "callback_data": "llamado_inicio"}],
                [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
            ]}
        )
    except Exception as e:
        logger.error(f"Error generando PDF: {e}")
        send_message(chat_id, f"Error generando el documento: {str(e)}\n\nIntenta de nuevo.",
            reply_markup={"inline_keyboard": [
                [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
            ]}
        )

def generar_pdf_llamado(estado):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle('titulo', parent=styles['Normal'], fontSize=13, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=6)
    subtitulo = ParagraphStyle('subtitulo', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=4)
    normal = ParagraphStyle('normal', parent=styles['Normal'], fontSize=10, fontName='Helvetica', spaceAfter=6, leading=14)
    negrita = ParagraphStyle('negrita', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', spaceAfter=4)
    justificado = ParagraphStyle('justificado', parent=styles['Normal'], fontSize=10, fontName='Helvetica', alignment=TA_JUSTIFY, spaceAfter=6, leading=14)
    
    aprendiz = estado.get("aprendiz", "")
    programa = PROGRAMAS.get(estado.get("programa", ""), "")
    ficha = estado.get("ficha", "")
    instructor = estado.get("instructor", "")
    tipo = estado.get("tipo_llamado", "disciplinario")
    numero = estado.get("numero_llamado", "primero")
    falta = estado.get("falta", "")
    descripcion = estado.get("descripcion", "")
    mes = estado.get("mes_falta", "")
    dias = estado.get("dias_falta", "")
    fecha_doc = datetime.now().strftime("%d de %B de %Y")
    
    numero_texto = "PRIMER" if numero == "primero" else "SEGUNDO"
    tipo_texto = "DISCIPLINARIO" if tipo == "disciplinario" else "ACADÉMICO"
    
    if "inasistencia" in falta.lower() or "ausencia" in falta.lower():
        descripcion_falta = f"inasistencias injustificadas durante el mes de {mes}, específicamente los días {dias}"
        articulo = "Art. 8 lit. d y Art. 16 del Acuerdo 0009 de 2024"
        consecuencia = "La acumulación de inasistencias injustificadas puede generar la cancelación del contrato de aprendizaje según lo establecido en el Art. 19 del mismo Acuerdo."
    elif "consumo" in falta.lower() or "sustancia" in falta.lower():
        descripcion_falta = descripcion or falta
        articulo = "Art. 8 lit. c y Art. 20 del Acuerdo 0009 de 2024"
        consecuencia = "Esta conducta constituye causal de cancelación inmediata de la matrícula según el Art. 20 del Acuerdo 0009 de 2024."
    elif "epp" in falta.lower() or "uniforme" in falta.lower():
        descripcion_falta = descripcion or falta
        articulo = "Art. 8 lit. a y Art. 12 lit. f del Acuerdo 0009 de 2024"
        consecuencia = "El incumplimiento reiterado de las normas de seguridad puede generar sanciones disciplinarias más severas."
    elif tipo == "academico":
        descripcion_falta = descripcion or falta
        articulo = "Art. 8 lit. d y Art. 28 del Acuerdo 0009 de 2024"
        consecuencia = "El no cumplimiento de los compromisos académicos puede generar un Plan de Mejoramiento obligatorio según el Art. 23 del Acuerdo 0009 de 2024."
    else:
        descripcion_falta = descripcion or falta
        articulo = "Art. 8 lit. f y Art. 12 lit. f del Acuerdo 0009 de 2024"
        consecuencia = "La reincidencia en esta conducta puede generar sanciones disciplinarias más severas según el Acuerdo 0009 de 2024."
    
    historia = []
    
    historia.append(Paragraph("SERVICIO NACIONAL DE APRENDIZAJE — SENA", titulo))
    historia.append(Paragraph("Centro Nacional Colombo Alemán", subtitulo))
    historia.append(Paragraph("Área de Metalmecánica", subtitulo))
    historia.append(Spacer(1, 0.3*cm))
    historia.append(Paragraph(f"{numero_texto} LLAMADO DE ATENCIÓN {tipo_texto}", titulo))
    historia.append(Paragraph(f"Acuerdo 0009 de 2024 — Reglamento del Aprendiz SENA", subtitulo))
    historia.append(Spacer(1, 0.5*cm))
    
    datos = [
        ["Aprendiz:", aprendiz, "Fecha:", fecha_doc],
        ["Programa:", programa, "Ficha:", ficha],
        ["Instructor(es):", instructor, "", ""],
    ]
    
    tabla = Table(datos, colWidths=[3.5*cm, 8*cm, 2.5*cm, 4*cm])
    tabla.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('BACKGROUND', (2,0), (2,-1), colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('SPAN', (1,2), (3,2)),
    ]))
    historia.append(tabla)
    historia.append(Spacer(1, 0.5*cm))
    
    historia.append(Paragraph("MOTIVO DEL LLAMADO DE ATENCIÓN", negrita))
    historia.append(Paragraph(
        f"El(la) instructor(a) <b>{instructor}</b> hace constar que el aprendiz <b>{aprendiz}</b>, "
        f"perteneciente al programa de formación <b>{programa}</b>, ficha <b>{ficha}</b>, "
        f"ha incurrido en la siguiente falta: <b>{descripcion_falta}</b>, "
        f"lo cual constituye una infracción al <b>{articulo}</b>.",
        justificado
    ))
    historia.append(Spacer(1, 0.3*cm))
    
    historia.append(Paragraph("CONSECUENCIAS Y COMPROMISOS", negrita))
    historia.append(Paragraph(consecuencia, justificado))
    historia.append(Spacer(1, 0.2*cm))
    historia.append(Paragraph(
        "Por medio del presente documento, se hace un llamado formal al aprendiz para que "
        "reflexione sobre su comportamiento y asuma los compromisos necesarios para continuar "
        "su proceso de formación de manera satisfactoria. Se espera una mejora inmediata y "
        "sostenida en la situación descrita.",
        justificado
    ))
    historia.append(Spacer(1, 0.5*cm))
    
    historia.append(Paragraph("FIRMAS", negrita))
    firmas = [
        ["", ""],
        ["_" * 35, "_" * 35],
        ["Instructor(a)", "Aprendiz"],
        [instructor, aprendiz],
        ["", ""],
        ["_" * 35, ""],
        ["Coordinador(a) Académico(a)", ""],
        ["Centro Nacional Colombo Alemán", ""],
    ]
    
    tabla_firmas = Table(firmas, colWidths=[9*cm, 9*cm])
    tabla_firmas.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME', (0,2), (-1,2), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    historia.append(tabla_firmas)
    historia.append(Spacer(1, 0.5*cm))
    
    historia.append(Paragraph(
        f"Documento generado el {fecha_doc} por el Sistema de Seguimiento a la Formación — "
        f"Centro Nacional Colombo Alemán, conforme al Acuerdo 0009 de 2024.",
        ParagraphStyle('pie', parent=styles['Normal'], fontSize=7, fontName='Helvetica', alignment=TA_CENTER, textColor=colors.grey)
    ))
    
    doc.build(historia)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()

        if "callback_query" in data:
            cb = data["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            cb_data = cb["data"]
            answer_callback(cb["id"])
            estado = get_estado(chat_id)

            if cb_data == "menu_principal":
                menu_principal(chat_id)

            elif cb_data == "menu_seguimiento":
                set_estado(chat_id, {"modo": "seguimiento", "historial": []})
                send_message(chat_id,
                    "📊 *Seguimiento a la Formación*\n\n"
                    "Descríbeme la novedad del aprendiz en lenguaje natural:\n\n"
                    "_Ejemplo: Carlos Gómez de la ficha PCMCNC-5 lleva 4 fallas injustificadas este trimestre_"
                )

            elif cb_data == "llamado_inicio":
                llamado_paso1_aprendiz(chat_id)

            elif cb_data == "menu_reglamento":
                set_estado(chat_id, {"modo": "reglamento", "historial": []})
                send_message(chat_id,
                    "📖 *Consulta del Reglamento*\n\n"
                    "¿Qué deseas consultar del Acuerdo 0009 de 2024?\n\n"
                    "_Ejemplo: ¿Cuántas fallas justifican un llamado de atención?_"
                )

            elif cb_data == "menu_plan":
                set_estado(chat_id, {"modo": "plan", "paso": "esperar_juicios"})
                send_message(chat_id,
                    "📝 *Generar Plan Concertado*\n\n"
                    "Por favor adjunta el archivo de *Juicios Evaluativos* (Excel) de la ficha.\n\n"
                    "_El agente extraerá automáticamente el programa, ficha y lista de aprendices._"
                )

            elif cb_data.startswith("prog_"):
                prog = cb_data.replace("prog_", "")
                estado["programa"] = prog
                set_estado(chat_id, estado)
                llamado_paso3_ficha_instructor(chat_id)

            elif cb_data.startswith("inst_"):
                inst = cb_data.replace("inst_", "")
                estado["instructor"] = inst
                set_estado(chat_id, estado)
                llamado_paso4_tipo(chat_id)

            elif cb_data.startswith("tipo_"):
                tipo = cb_data.replace("tipo_", "")
                estado["tipo_llamado"] = tipo
                set_estado(chat_id, estado)
                llamado_paso5_numero(chat_id)

            elif cb_data.startswith("num_"):
                num = cb_data.replace("num_", "")
                estado["numero_llamado"] = num
                set_estado(chat_id, estado)
                llamado_paso6_falta(chat_id)

            elif cb_data.startswith("falta_"):
                idx = int(cb_data.replace("falta_", ""))
                if estado.get("tipo_llamado") == "disciplinario":
                    falta = FALTAS_DISCIPLINARIAS[idx]
                else:
                    falta = FALTAS_ACADEMICAS[idx]
                estado["falta"] = falta
                set_estado(chat_id, estado)
                llamado_paso7_detalles(chat_id)

            elif cb_data.startswith("mes_"):
                mes = cb_data.replace("mes_", "")
                estado["mes_falta"] = mes
                set_estado(chat_id, estado)
                llamado_dias_inasistencia(chat_id)

            elif cb_data == "generar_llamado":
                llamado_generar_pdf(chat_id)

            elif cb_data == "nueva_novedad":
                set_estado(chat_id, {"modo": "seguimiento", "historial": []})
                send_message(chat_id, "📊 Cuéntame la nueva novedad:")

            return jsonify({"ok": True})

        if "message" not in data:
            return jsonify({"ok": True})

        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        user = message.get("from", {})
        username = user.get("username", "")

        logger.info(f"Msg @{username}: {text[:50]}")

        if not text:
            return jsonify({"ok": True})

        if text in ["/start", "/menu"]:
            menu_principal(chat_id)
            return jsonify({"ok": True})

        if text == "/nuevo":
            menu_principal(chat_id)
            return jsonify({"ok": True})

        estado = get_estado(chat_id)
        modo = estado.get("modo", "menu")
        paso = estado.get("paso", "")

        # ── FLUJO LLAMADO DE ATENCIÓN ──
        if modo == "llamado":
            if paso == "aprendiz":
                estado["aprendiz"] = text.strip().title()
                set_estado(chat_id, estado)
                llamado_paso2_formacion(chat_id)

            elif paso == "ficha":
                estado["ficha"] = text.strip()
                set_estado(chat_id, estado)
                llamado_paso3b_instructor(chat_id)

            elif paso == "detalles":
                estado["descripcion"] = text.strip()
                set_estado(chat_id, estado)
                resumen = (
                    f"📋 *Resumen del Llamado de Atención*\n\n"
                    f"• *Aprendiz:* {estado.get('aprendiz')}\n"
                    f"• *Programa:* {PROGRAMAS.get(estado.get('programa',''), '')}\n"
                    f"• *Ficha:* {estado.get('ficha')}\n"
                    f"• *Instructor:* {estado.get('instructor')}\n"
                    f"• *Tipo:* {estado.get('tipo_llamado','').capitalize()}\n"
                    f"• *Número:* {estado.get('numero_llamado','').capitalize()} llamado\n"
                    f"• *Falta:* {estado.get('falta')}\n"
                    f"• *Descripción:* {text.strip()}\n\n"
                    f"¿Generamos el documento?"
                )
                send_message(chat_id, resumen,
                    reply_markup={"inline_keyboard": [
                        [{"text": "✅ Generar PDF", "callback_data": "generar_llamado"},
                         {"text": "❌ Cancelar", "callback_data": "menu_principal"}]
                    ]}
                )

            elif paso == "dias_falta":
                estado["dias_falta"] = text.strip()
                set_estado(chat_id, estado)
                resumen = (
                    f"📋 *Resumen del Llamado de Atención*\n\n"
                    f"• *Aprendiz:* {estado.get('aprendiz')}\n"
                    f"• *Programa:* {PROGRAMAS.get(estado.get('programa',''), '')}\n"
                    f"• *Ficha:* {estado.get('ficha')}\n"
                    f"• *Instructor:* {estado.get('instructor')}\n"
                    f"• *Tipo:* {estado.get('tipo_llamado','').capitalize()}\n"
                    f"• *Número:* {estado.get('numero_llamado','').capitalize()} llamado\n"
                    f"• *Falta:* {estado.get('falta')}\n"
                    f"• *Mes:* {estado.get('mes_falta','').capitalize()}\n"
                    f"• *Días:* {text.strip()}\n\n"
                    f"¿Generamos el documento?"
                )
                send_message(chat_id, resumen,
                    reply_markup={"inline_keyboard": [
                        [{"text": "✅ Generar PDF", "callback_data": "generar_llamado"},
                         {"text": "❌ Cancelar", "callback_data": "menu_principal"}]
                    ]}
                )

        # ── FLUJO SEGUIMIENTO ──
        elif modo == "seguimiento":
            if "historial" not in estado:
                estado["historial"] = []
            estado["historial"].append({"role": "user", "content": text})
            send_typing(chat_id)
            respuesta = consultar_groq(estado["historial"], SYSTEM_ANALISIS)
            if respuesta:
                estado["historial"].append({"role": "assistant", "content": respuesta})
                set_estado(chat_id, estado)
                send_message(chat_id, respuesta,
                    reply_markup={"inline_keyboard": [
                        [{"text": "📋 Generar Llamado de Atención", "callback_data": "llamado_inicio"}],
                        [{"text": "🔄 Nueva novedad", "callback_data": "nueva_novedad"},
                         {"text": "🏠 Menú", "callback_data": "menu_principal"}]
                    ]}
                )
            else:
                send_message(chat_id, "Error procesando. Intenta de nuevo.")

        # ── FLUJO REGLAMENTO ──
        elif modo == "reglamento":
            if "historial" not in estado:
                estado["historial"] = []
            estado["historial"].append({"role": "user", "content": text})
            send_typing(chat_id)
            system_reg = """Eres un experto en el Reglamento del Aprendiz SENA, específicamente el Acuerdo 0009 de 2024. 
Respondes preguntas citando el artículo exacto y explicando su aplicación práctica de forma clara y concisa. 
Responde en español."""
            respuesta = consultar_groq(estado["historial"], system_reg)
            if respuesta:
                estado["historial"].append({"role": "assistant", "content": respuesta})
                set_estado(chat_id, estado)
                send_message(chat_id, respuesta,
                    reply_markup={"inline_keyboard": [
                        [{"text": "❓ Otra consulta", "callback_data": "menu_reglamento"}],
                        [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
                    ]}
                )
            else:
                send_message(chat_id, "Error procesando. Intenta de nuevo.")

        else:
            # Si escribe algo fuera de flujo
            texto_lower = text.lower()
            if "llamado" in texto_lower:
                llamado_paso1_aprendiz(chat_id)
            elif "reglamento" in texto_lower or "acuerdo" in texto_lower:
                set_estado(chat_id, {"modo": "reglamento", "historial": [{"role": "user", "content": text}]})
                send_typing(chat_id)
                system_reg = "Eres experto en el Acuerdo 0009 de 2024 SENA. Responde citando artículos exactos."
                respuesta = consultar_groq([{"role": "user", "content": text}], system_reg)
                if respuesta:
                    send_message(chat_id, respuesta,
                        reply_markup={"inline_keyboard": [
                            [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
                        ]}
                    )
            else:
                # Analizar como novedad directamente
                set_estado(chat_id, {"modo": "seguimiento", "historial": [{"role": "user", "content": text}]})
                send_typing(chat_id)
                respuesta = consultar_groq([{"role": "user", "content": text}], SYSTEM_ANALISIS)
                if respuesta:
                    send_message(chat_id, respuesta,
                        reply_markup={"inline_keyboard": [
                            [{"text": "📋 Generar Llamado de Atención", "callback_data": "llamado_inicio"}],
                            [{"text": "🏠 Menú", "callback_data": "menu_principal"}]
                        ]}
                    )

        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Error webhook: {e}")
        return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Agente SENA activo", "bot": "@AgenteMecanizadoSena_bot"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
