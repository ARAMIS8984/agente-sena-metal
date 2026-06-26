import os
import json
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ALLOWED_USERS = os.environ.get("ALLOWED_USERS", "").split(",")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

conversaciones = {}

SYSTEM_PROMPT = """Eres el Agente SENA Metalmecánica, asistente inteligente del área de Metalmecánica del Centro Nacional Colombo Alemán (SENA Regional Atlántico), Barranquilla.

Tu función es ayudar a los instructores a gestionar novedades de sus fichas y generar documentos oficiales SENA.

DOCUMENTOS QUE GESTIONAS:
1. Llamado de Atención - ausencias injustificadas o incumplimientos
2. Plan de Mejoramiento - notas bajas o falta de evidencias
3. Plan Concertado - acuerdo pedagógico instructor-aprendiz
4. Seguimiento a la Formación - consulta asistencia y avance
5. Acta Extraordinaria - situaciones especiales
6. Reconocimiento - desempeño destacado
7. Consulta Reglamento - basado en Acuerdo 0009 de 2024

REGLAS ACUERDO 0009 DE 2024:
- 3+ ausencias injustificadas en trimestre → Llamado de Atención tipo 1
- 5+ ausencias injustificadas → Llamado tipo 2 + Plan de Mejoramiento
- Nota < 3.0 en competencia → Plan de Mejoramiento obligatorio
- Más del 40% de evidencias sin entregar → Plan de Mejoramiento
- Nota >= 4.5 en todas las competencias → Reconocimiento

TRIMESTRES:
- T1: enero-marzo | T2: abril-junio | T3: julio-septiembre | T4: octubre-diciembre

COMPORTAMIENTO:
- Identifica siempre: nombre del aprendiz y ficha del mensaje
- Si no viene el trimestre → pregunta UNA sola vez: "¿Guardo en [trimestre actual] o es otro?"
- Aplica reglas automáticamente y propone el documento
- Confirma antes de generar: "¿Genero [documento] para [aprendiz]?"
- Al confirmar → responde con JSON de acción al final así exactamente:
  [ACCION:{"tipo":"llamado","aprendiz":"Juan Perez","ficha":"PCMCNC-5","trimestre":"T2-2026"}]
- Tipos válidos: llamado, plan_mejora, plan_concertado, acta, reconocimiento, seguimiento
- Responde siempre en español, conciso y directo
- Para preguntas del reglamento responde basándote en el Acuerdo 0009 de 2024

INSTRUCTORES: Aramis Vitola, Carlos Charris, Carlos Sabalza, Wilfrido Romero, Ana Maria Barrios, Omar Pardey."""

def get_trimestre_actual():
    mes = datetime.now().month
    year = datetime.now().year
    if mes <= 3: return f"T1-{year}"
    elif mes <= 6: return f"T2-{year}"
    elif mes <= 9: return f"T3-{year}"
    else: return f"T4-{year}"

def send_telegram_message(chat_id, text):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=30)
    except Exception as e:
        logger.error(f"Error Telegram: {e}")

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction", json={
            "chat_id": chat_id, "action": "typing"
        }, timeout=10)
    except:
        pass

def consultar_gemini(chat_id, mensaje_usuario):
    if chat_id not in conversaciones:
        conversaciones[chat_id] = []

    conversaciones[chat_id].append({
        "role": "user",
        "parts": [{"text": mensaje_usuario}]
    })

    if len(conversaciones[chat_id]) > 20:
        conversaciones[chat_id] = conversaciones[chat_id][-20:]

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": conversaciones[chat_id],
        "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.3}
    }

    try:
        response = requests.post(GEMINI_URL, json=payload, timeout=30)
        data = response.json()
        respuesta_completa = data["candidates"][0]["content"]["parts"][0]["text"]

        respuesta_limpia = respuesta_completa
        ruta_guardado = None

        if "[ACCION:" in respuesta_completa:
            inicio = respuesta_completa.index("[ACCION:")
            fin = respuesta_completa.index("]", inicio) + 1
            accion_str = respuesta_completa[inicio+8:fin-1]
            respuesta_limpia = respuesta_completa[:inicio].strip()
            try:
                accion = json.loads(accion_str)
                tipo = accion.get("tipo","doc")
                aprendiz = accion.get("aprendiz","Aprendiz")
                ficha = accion.get("ficha","sin-ficha")
                trimestre = accion.get("trimestre", get_trimestre_actual())
                apellido = aprendiz.split()[-1]
                fecha = datetime.now().strftime("%Y%m%d")
                nombres = {
                    "llamado": f"Llamado_{apellido}_{fecha}.pdf",
                    "plan_mejora": f"PlanMejora_{apellido}_{fecha}.pdf",
                    "plan_concertado": f"PlanConcertado_{apellido}_{fecha}.pdf",
                    "acta": f"Acta_{fecha}.pdf",
                    "reconocimiento": f"Reconocimiento_{apellido}_{fecha}.pdf",
                    "seguimiento": f"Seguimiento_{fecha}.xlsx"
                }
                nombre_archivo = nombres.get(tipo, f"Documento_{fecha}.pdf")
                ruta_guardado = f"SENA-Agente/Fichas/{ficha}/{trimestre}/{nombre_archivo}"
            except Exception as e:
                logger.error(f"Error parseando accion: {e}")

        conversaciones[chat_id].append({
            "role": "model",
            "parts": [{"text": respuesta_limpia}]
        })

        return respuesta_limpia, ruta_guardado

    except Exception as e:
        logger.error(f"Error Gemini: {e}")
        return "Error procesando tu solicitud. Intenta de nuevo.", None

def es_autorizado(username, user_id):
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
                "Gestiono novedades y genero documentos oficiales.\n\n"
                "Ejemplo:\n"
                "_\"Aprendiz Juan Pérez, ficha PCMCNC-5, tiene 4 fallas injustificadas\"_\n\n"
                "Comandos:\n"
                "/nuevo - Reiniciar conversación\n"
                "/ayuda - Ver qué puedo hacer"
            )
            return jsonify({"ok": True})

        if text == "/nuevo":
            conversaciones.pop(chat_id, None)
            send_telegram_message(chat_id, "Conversación reiniciada. Cuéntame la novedad.")
            return jsonify({"ok": True})

        if text == "/ayuda":
            send_telegram_message(chat_id,
                "*Documentos que puedo generar:*\n"
                "• Llamado de Atención\n"
                "• Plan de Mejoramiento\n"
                "• Plan Concertado\n"
                "• Acta Extraordinaria\n"
                "• Reconocimiento\n\n"
                "*También puedo:*\n"
                "• Consultar el Seguimiento de una ficha\n"
                "• Responder preguntas del Acuerdo 0009\n\n"
                "Solo descríbeme la novedad en lenguaje natural."
            )
            return jsonify({"ok": True})

        if not es_autorizado(username, user_id):
            send_telegram_message(chat_id, "No tienes autorización. Contacta a Aramis Vitola.")
            return jsonify({"ok": True})

        send_typing(chat_id)
        respuesta, ruta = consultar_gemini(chat_id, text)

        if ruta:
            respuesta += f"\n\n📁 `{ruta}`"

        send_telegram_message(chat_id, respuesta)
        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Error webhook: {e}")
        return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Agente SENA activo", "bot": "@AgenteMecanizadoSena_bot"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
