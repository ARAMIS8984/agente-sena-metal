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
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ALLOWED_USERS = os.environ.get("ALLOWED_USERS", "").split(",")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

conversaciones = {}

SYSTEM_PROMPT = """Eres el Agente SENA Metalmecánica del Centro Nacional Colombo Alemán, Barranquilla. Asistes a instructores del área de Metalmecánica.

Cuando recibes una novedad sobre un aprendiz, respondes SIEMPRE con este formato exacto en un solo mensaje, sin preguntas:

---
🎓 *ANÁLISIS DE NOVEDAD*
*Aprendiz:* [nombre]
*Ficha:* [codigo]
*Trimestre:* [T1/T2/T3/T4-año]

📋 *SITUACIÓN:*
[Explica brevemente la situación del aprendiz y su gravedad]

⚖️ *NORMA APLICABLE:*
[Cita el artículo exacto del Acuerdo 0009 de 2024 que aplica]

✅ *PROCEDIMIENTO COMO INSTRUCTOR:*
1. [Paso 1]
2. [Paso 2]
3. [Paso 3]

📄 *DOCUMENTO A GENERAR:* [nombre del documento]
---

REGLAS DEL ACUERDO 0009 DE 2024:

INASISTENCIAS:
- Art. 15: El aprendiz debe cumplir con el 80% de asistencia mínima
- Art. 16: 3 ausencias injustificadas en el trimestre → Llamado de Atención tipo 1 por escrito
- Art. 17: 5 o más ausencias injustificadas → Llamado de Atención tipo 2 + Plan de Mejoramiento obligatorio
- Art. 18: Más del 20% de inasistencias totales → riesgo de desvinculación del programa

DESEMPEÑO ACADÉMICO:
- Art. 22: Nota mínima aprobatoria por competencia es 3.0 sobre 5.0
- Art. 23: Nota menor a 3.0 → Plan de Mejoramiento obligatorio con fecha límite
- Art. 24: Si no supera el Plan de Mejoramiento → segunda oportunidad con Acta Extraordinaria
- Art. 25: Nota 4.5 o superior en todas las competencias → Reconocimiento por desempeño destacado

EVIDENCIAS:
- Art. 28: El aprendiz debe entregar mínimo el 60% de evidencias por competencia
- Art. 29: Menos del 60% de evidencias → Plan de Mejoramiento con cronograma de entrega
- Art. 30: Incumplimiento reiterado → Llamado de Atención + Plan de Mejoramiento

PLAN CONCERTADO:
- Art. 35: Al inicio de cada trimestre se firma el Plan Concertado entre instructor y aprendiz
- Art. 36: El Plan Concertado define compromisos, estrategias y fechas de entrega

PROCEDIMIENTOS:
- Llamado de Atención: Se notifica al aprendiz por escrito, firma el documento, se archiva en carpeta del aprendiz
- Plan de Mejoramiento: Se define con el aprendiz, incluye actividades, fechas y criterios de superación
- Acta Extraordinaria: Se elabora con coordinación académica para casos especiales
- Reconocimiento: Se registra en hoja de vida del aprendiz y se informa a coordinación

TRIMESTRES: T1 enero-marzo, T2 abril-junio, T3 julio-septiembre, T4 octubre-diciembre

Si no viene el trimestre en el mensaje, usa el trimestre actual según la fecha de hoy.
Si no viene la ficha, indica [FICHA PENDIENTE] y continúa con el análisis.

Responde siempre en español. Sé preciso, profesional y directo."""

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
        if r.status_code != 200:
            # Reintenta sin markdown si falla
            requests.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": text.replace("*","").replace("_","").replace("`","")
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

def consultar_groq(chat_id, mensaje_usuario):
    if chat_id not in conversaciones:
        conversaciones[chat_id] = []

    conversaciones[chat_id].append({
        "role": "user",
        "content": mensaje_usuario
    })

    if len(conversaciones[chat_id]) > 10:
        conversaciones[chat_id] = conversaciones[chat_id][-10:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversaciones[chat_id]

    try:
        response = requests.post(GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.2
            },
            timeout=30
        )

        logger.info(f"Groq status: {response.status_code}")
        data = response.json()

        if response.status_code != 200:
            logger.error(f"Groq error: {data}")
            return "Error procesando tu solicitud. Intenta de nuevo.", None

        respuesta = data["choices"][0]["message"]["content"]

        conversaciones[chat_id].append({
            "role": "assistant",
            "content": respuesta
        })

        return respuesta, None

    except Exception as e:
        logger.error(f"Error Groq: {e}")
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

        logger.info(f"Mensaje de @{username} (id:{user_id}): {text}")

        if not text:
            return jsonify({"ok": True})

        if text == "/start":
            send_telegram_message(chat_id,
                "Hola! Soy el *Agente SENA Metalmecanica*.\n\n"
                "Describeme la novedad del aprendiz y te entrego:\n"
                "- Analisis de la situacion\n"
                "- Articulo del reglamento aplicable\n"
                "- Procedimiento a seguir\n"
                "- Documento a generar\n\n"
                "Ejemplo:\n"
                "_Aprendiz Carlos Gomez, ficha PCMCNC-5, tiene 4 fallas injustificadas_\n\n"
                "/nuevo - Reiniciar\n/ayuda - Ver funciones"
            )
            return jsonify({"ok": True})

        if text == "/nuevo":
            conversaciones.pop(chat_id, None)
            send_telegram_message(chat_id, "Listo. Cuentame la novedad.")
            return jsonify({"ok": True})

        if text == "/ayuda":
            send_telegram_message(chat_id,
                "*Novedades que proceso:*\n"
                "- Ausencias injustificadas\n"
                "- Notas bajas\n"
                "- Falta de evidencias\n"
                "- Incumplimiento de compromisos\n"
                "- Desempeno destacado\n"
                "- Situaciones especiales\n\n"
                "*Documentos que genero:*\n"
                "- Llamado de Atencion\n"
                "- Plan de Mejoramiento\n"
                "- Plan Concertado\n"
                "- Acta Extraordinaria\n"
                "- Reconocimiento\n\n"
                "Simplemente describeme la situacion en lenguaje natural."
            )
            return jsonify({"ok": True})

        if not es_autorizado(username, user_id):
            send_telegram_message(chat_id, "No tienes autorizacion. Contacta a Aramis Vitola.")
            return jsonify({"ok": True})

        send_typing(chat_id)
        respuesta, _ = consultar_groq(chat_id, text)
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
