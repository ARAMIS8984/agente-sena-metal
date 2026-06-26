import os
import json
import logging
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ONEDRIVE_TOKEN = os.environ.get("ONEDRIVE_TOKEN")
ALLOWED_USERS = os.environ.get("ALLOWED_USERS", "").split(",")

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

conversaciones = {}

SYSTEM_PROMPT = """Eres el Agente SENA Metalmecánica, asistente inteligente del área de Metalmecánica del Centro Nacional Colombo Alemán (SENA Regional Atlántico).

Tu función es ayudar a los instructores a gestionar novedades de sus fichas de formación y generar documentos oficiales SENA.

DOCUMENTOS QUE PUEDES GESTIONAR:
1. Llamado de Atención - cuando un aprendiz tiene ausencias injustificadas o incumplimientos
2. Plan de Mejoramiento - cuando un aprendiz tiene notas bajas o no entrega evidencias
3. Plan Concertado - acuerdo pedagógico entre instructor y aprendiz
4. Seguimiento a la Formación - consulta de asistencia y avance del grupo
5. Acta Extraordinaria - situaciones especiales que requieren registro formal
6. Reconocimiento - aprendiz con desempeño destacado
7. Consulta del Reglamento - respuestas basadas en el Acuerdo 0009 de 2024

REGLAS SENA (Acuerdo 0009 de 2024):
- 3 o más ausencias injustificadas en el trimestre → Llamado de Atención tipo 1
- 5 o más ausencias injustificadas → Llamado de Atención tipo 2 + Plan de Mejoramiento
- Nota inferior a 3.0 en competencia → Plan de Mejoramiento obligatorio
- Aprendiz que no entrega más del 40% de evidencias → Plan de Mejoramiento
- Desempeño superior (nota >= 4.5 en todas las competencias) → Reconocimiento

COMPORTAMIENTO:
- Cuando el instructor reporte una novedad, identifica SIEMPRE: nombre del aprendiz y ficha.
- Si la ficha viene en el mensaje → úsala directamente.
- Si NO viene el trimestre → pregunta: "¿Guardo en T[actual] o es otro trimestre?" (una sola pregunta).
- Aplica las reglas automáticamente y propone el documento correspondiente.
- Confirma antes de generar: "¿Genero el [documento] para [aprendiz]?"
- Al guardar confirma: "Guardado en [ficha]/[trimestre]/[nombre_archivo].pdf"
- Responde siempre en español, de forma concisa y clara.
- Si te preguntan por el reglamento, responde basándote en el Acuerdo 0009 de 2024.

INSTRUCTORES AUTORIZADOS: Aramis Vitola, Carlos Charris, Carlos Sabalza, Wilfrido Romero, Ana Maria Barrios, Omar Pardey.

TRIMESTRES DEL AÑO:
- T1: enero - marzo
- T2: abril - junio  
- T3: julio - septiembre
- T4: octubre - diciembre

Cuando determines qué documento generar, responde con este JSON al final de tu mensaje (invisible para el usuario):
[ACCION:{"tipo":"llamado|plan_mejora|plan_concertado|acta|reconocimiento|seguimiento","aprendiz":"nombre","ficha":"codigo","trimestre":"T2-2026"}]
"""

def send_telegram_message(chat_id, text):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        logger.error(f"Error enviando mensaje Telegram: {e}")

def send_typing(chat_id):
    requests.post(f"{TELEGRAM_API}/sendChatAction", json={
        "chat_id": chat_id,
        "action": "typing"
    }, timeout=10)

def get_trimestre_actual():
    from datetime import datetime
    mes = datetime.now().month
    year = datetime.now().year
    if mes <= 3:
        return f"T1-{year}"
    elif mes <= 6:
        return f"T2-{year}"
    elif mes <= 9:
        return f"T3-{year}"
    else:
        return f"T4-{year}"

def procesar_accion(accion_json, chat_id):
    try:
        tipo = accion_json.get("tipo")
        aprendiz = accion_json.get("aprendiz", "Aprendiz")
        ficha = accion_json.get("ficha", "sin-ficha")
        trimestre = accion_json.get("trimestre", get_trimestre_actual())

        apellido = aprendiz.split()[-1] if aprendiz else "Aprendiz"
        from datetime import datetime
        fecha = datetime.now().strftime("%Y%m%d")

        nombres_archivo = {
            "llamado": f"Llamado_{apellido}_{fecha}.pdf",
            "plan_mejora": f"PlanMejora_{apellido}_{fecha}.pdf",
            "plan_concertado": f"PlanConcertado_{apellido}_{fecha}.pdf",
            "acta": f"Acta_{fecha}.pdf",
            "reconocimiento": f"Reconocimiento_{apellido}_{fecha}.pdf",
            "seguimiento": f"Seguimiento_{ficha}_{trimestre}.xlsx"
        }

        nombre_archivo = nombres_archivo.get(tipo, f"Documento_{fecha}.pdf")
        ruta = f"SENA-Agente/Fichas/{ficha}/{trimestre}/{nombre_archivo}"

        logger.info(f"Documento a guardar en OneDrive: {ruta}")
        return ruta

    except Exception as e:
        logger.error(f"Error procesando acción: {e}")
        return None

def consultar_agente(chat_id, mensaje_usuario):
    if chat_id not in conversaciones:
        conversaciones[chat_id] = []

    conversaciones[chat_id].append({
        "role": "user",
        "content": mensaje_usuario
    })

    if len(conversaciones[chat_id]) > 20:
        conversaciones[chat_id] = conversaciones[chat_id][-20:]

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=conversaciones[chat_id]
        )

        respuesta_completa = response.content[0].text

        respuesta_limpia = respuesta_completa
        ruta_guardado = None

        if "[ACCION:" in respuesta_completa:
            inicio = respuesta_completa.index("[ACCION:")
            fin = respuesta_completa.index("]", inicio) + 1
            accion_str = respuesta_completa[inicio+8:fin-1]
            respuesta_limpia = respuesta_completa[:inicio].strip()
            try:
                accion_json = json.loads(accion_str)
                ruta_guardado = procesar_accion(accion_json, chat_id)
            except:
                pass

        conversaciones[chat_id].append({
            "role": "assistant",
            "content": respuesta_limpia
        })

        return respuesta_limpia, ruta_guardado

    except Exception as e:
        logger.error(f"Error consultando agente: {e}")
        return "Lo siento, tuve un error procesando tu solicitud. Intenta de nuevo.", None

def es_usuario_autorizado(username, user_id):
    if not ALLOWED_USERS or ALLOWED_USERS == [""]:
        return True
    return username in ALLOWED_USERS or str(user_id) in ALLOWED_USERS

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()

        if "message" not in data:
            return jsonify({"ok": True})

        message = data["message"]
        chat_id = message["chat"]["id"]
        user = message.get("from", {})
        username = user.get("username", "")
        user_id = user.get("id", "")
        text = message.get("text", "")

        if not text:
            return jsonify({"ok": True})

        if text == "/start":
            send_telegram_message(chat_id,
                "Hola! Soy el *Agente SENA Metalmecánica*.\n\n"
                "Puedo ayudarte a gestionar novedades y generar documentos oficiales.\n\n"
                "Simplemente descríbeme la novedad, por ejemplo:\n"
                "_\"El aprendiz Juan Pérez, ficha PCMCNC-5, tiene 4 fallas injustificadas\"_\n\n"
                "Y yo me encargo del resto."
            )
            return jsonify({"ok": True})

        if text == "/nuevo":
            conversaciones.pop(chat_id, None)
            send_telegram_message(chat_id, "Conversación reiniciada. Cuéntame la novedad.")
            return jsonify({"ok": True})

        if not es_usuario_autorizado(username, user_id):
            send_telegram_message(chat_id, "No tienes autorización para usar este bot. Contacta al administrador.")
            return jsonify({"ok": True})

        send_typing(chat_id)

        respuesta, ruta = consultar_agente(chat_id, text)

        if ruta:
            respuesta += f"\n\n📁 `{ruta}`"

        send_telegram_message(chat_id, respuesta)

        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Agente SENA activo", "bot": "@AgenteMecanizadoSena_bot"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
