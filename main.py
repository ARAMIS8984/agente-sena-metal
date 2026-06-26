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

conversaciones = {}

SYSTEM_PROMPT = """Eres el Agente SENA Metalmecánica, asistente del área de Metalmecánica del Centro Nacional Colombo Alemán, Barranquilla.

Ayudas a instructores a gestionar novedades y generar documentos oficiales SENA.

DOCUMENTOS QUE GESTIONAS:
1. Llamado de Atención - ausencias o incumplimientos
2. Plan de Mejoramiento - notas bajas o falta de evidencias
3. Plan Concertado - acuerdo pedagógico
4. Seguimiento a la Formación - asistencia y avance
5. Acta Extraordinaria - situaciones especiales
6. Reconocimiento - desempeño destacado
7. Consulta Reglamento - Acuerdo 0009 de 2024

REGLAS ACUERDO 0009 DE 2024:
- 3+ ausencias injustificadas → Llamado de Atención tipo 1
- 5+ ausencias injustificadas → Llamado tipo 2 + Plan de Mejoramiento
- Nota menor a 3.0 → Plan de Mejoramiento
- Más del 40% de evidencias sin entregar → Plan de Mejoramiento
- Nota mayor o igual a 4.5 en todas → Reconocimiento

TRIMESTRES: T1 enero-marzo, T2 abril-junio, T3 julio-septiembre, T4 octubre-diciembre

INSTRUCCIONES:
- Identifica nombre del aprendiz y ficha del mensaje
- Si no viene trimestre pregunta: cual trimestre T1 T2 T3 o T4
- Aplica reglas y propone documento
- Confirma antes de generar
- Cuando confirmen generacion incluye al final: [ACCION:{"tipo":"llamado","aprendiz":"Juan Perez","ficha":"PCMCNC-5","trimestre":"T2-2026"}]
- Tipos: llamado, plan_mejora, plan_concertado, acta, reconocimiento, seguimiento
- Responde en español, breve y directo

INSTRUCTORES: Aramis Vitola, Carlos Charris, Carlos Sabalza, Wilfrido Romero, Ana Maria Barrios, Omar Pardey"""

def get_trimestre_actual():
    mes = datetime.now().month
    year = datetime.now().year
    if mes <= 3: return f"T1-{year}"
    elif mes <= 6: return f"T2-{year}"
    elif mes <= 9: return f"T3-{year}"
    else: return f"T4-{year}"

def send_telegram_message(chat_id, text):
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=30)
        logger.info(f"Telegram response: {r.status_code}")
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": conversaciones[chat_id],
        "generationConfig": {
            "maxOutputTokens": 800,
            "temperature": 0.3
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        logger.info(f"Gemini status: {response.status_code}")
        logger.info(f"Gemini response keys: {list(data.keys())}")

        candidates = data.get("candidates", [])
        if not candidates:
            error_msg = data.get("error", {}).get("message", "Sin respuesta")
            logger.error(f"Gemini sin candidates: {error_msg}")
            return "Lo siento, tuve un problema procesando tu solicitud. Intenta de nuevo.", None

        respuesta_completa = candidates[0]["content"]["parts"][0]["text"]
        respuesta_limpia = respuesta_completa
        ruta_guardado = None

        if "[ACCION:" in respuesta_completa:
            try:
                inicio = respuesta_completa.index("[ACCION:")
                fin = respuesta_completa.index("]", inicio) + 1
                accion_str = respuesta_completa[inicio+8:fin-1]
                respuesta_limpia = respuesta_completa[:inicio].strip()
                accion = json.loads(accion_str)
                tipo = accion.get("tipo", "doc")
                aprendiz = accion.get("aprendiz", "Aprendiz")
                ficha = accion.get("ficha", "sin-ficha")
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
        return "Error de conexion. Intenta de nuevo.", None

def es_autorizado(username, user_id):
    if not ALLOWED_USERS or ALLOWED_USERS == [""]:
        return True
    return username in ALLOWED_USERS or str(user_id) in ALLOWED_USERS

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data or "message" not in data:
            return jsonify({"ok": True})

        message = data["message"]
        chat_id = message["chat"]["id"]
        user = message.get("from", {})
        username = user.get("username", "")
        user_id = user.get("id", "")
        text = message.get("text", "")

        logger.info(f"Mensaje de @{username}: {text}")

        if not text:
            return jsonify({"ok": True})

        if text == "/start":
            send_telegram_message(chat_id,
                "Hola! Soy el *Agente SENA Metalmecanica*.\n\n"
                "Gestiono novedades y documentos oficiales.\n\n"
                "Ejemplo:\n"
                "_Aprendiz Juan Perez, ficha PCMCNC-5, tiene 4 fallas injustificadas_\n\n"
                "/nuevo - Reiniciar\n/ayuda - Ver funciones"
            )
            return jsonify({"ok": True})

        if text == "/nuevo":
            conversaciones.pop(chat_id, None)
            send_telegram_message(chat_id, "Conversacion reiniciada. Cuentame la novedad.")
            return jsonify({"ok": True})

        if text == "/ayuda":
            send_telegram_message(chat_id,
                "*Puedo generar:*\n"
                "Llamado de Atencion\n"
                "Plan de Mejoramiento\n"
                "Plan Concertado\n"
                "Acta Extraordinaria\n"
                "Reconocimiento\n\n"
                "*Y consultar:*\n"
                "Seguimiento de ficha\n"
                "Reglamento Acuerdo 0009"
            )
            return jsonify({"ok": True})

        if not es_autorizado(username, user_id):
            send_telegram_message(chat_id, "No tienes autorizacion. Contacta a Aramis Vitola.")
            return jsonify({"ok": True})

        send_typing(chat_id)
        respuesta, ruta = consultar_gemini(chat_id, text)

        if ruta:
            respuesta += f"\n\n Guardado en:\n`{ruta}`"

        send_telegram_message(chat_id, respuesta)
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
